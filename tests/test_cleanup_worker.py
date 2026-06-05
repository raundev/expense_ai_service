"""Soft Delete 물리 정리 워커 검증 (Phase D, 설계 §4.3).

- 정상: 봇 Soft Delete → 소속 문서 cascade DELETING → cleanup 이 벡터/파일/행 + 봇 행 물리삭제.
- 멱등: 재실행해도 안전(0건).
- 엣지: Qdrant 삭제 실패 시 롤백 → 문서/봇 DELETING 유지 → 다음 주기 재시도로 결국 정리(좀비벡터 방지).
"""
from __future__ import annotations

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client import models as qmodels
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.vector_store import COLLECTION_NAME
from app.core.dependencies import TenantContext
from app.models import Base
from app.models.bots import Bot
from app.models.documents import Document
from app.schemas.bots import BotCreateRequest
from app.schemas.documents import DocumentIngestTextRequest
from app.services.bot_service import BotService
from app.services.cleanup_service import run_cleanup
from app.services.document_service import DocumentService

_DIM = 256
TENANT = TenantContext(company_id="C1", workplace_id="W1")


class _FailingClient:
    def delete(self, **_kw):
        raise RuntimeError("Qdrant unreachable")


class _FailingVS:
    """벡터 삭제가 항상 실패하는 스토어 더블(네트워크 장애 시뮬레이션)."""

    def __init__(self, collection_name: str):
        self.client = _FailingClient()
        self.collection_name = collection_name


@pytest.fixture
def vs():
    qc = QdrantClient(location=":memory:")
    qc.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=qmodels.VectorParams(size=_DIM, distance=qmodels.Distance.COSINE),
    )
    return QdrantVectorStore(
        client=qc,
        collection_name=COLLECTION_NAME,
        embedding=DeterministicFakeEmbedding(size=_DIM),
    )


@pytest.fixture
def db():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(eng)
    session = sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        eng.dispose()


def _make_bot_with_docs(db, vs, tmp_path):
    """봇 + 임베딩 문서(벡터) + 파일 문서(디스크) 구성. 반환: (bot, doc_vec, doc_file, file_path)."""
    bot = BotService(db).create_bot(BotCreateRequest(name="B"), TENANT)
    BotService(db).set_disabled(bot.id, TENANT, disabled=False)

    docsvc = DocumentService(db, vector_store=vs)
    doc_vec = docsvc.ingest_text(
        TENANT,
        DocumentIngestTextRequest(
            text="사내 규정 본문입니다. 연차는 15일입니다.", source_name="규정",
            owner_id=bot.id, domain="policy", is_compliance_source=False,
        ),
    )
    # 파일 기반 문서(임베딩 없이 파일만) — 파일 삭제 경로 검증용
    f = tmp_path / "rule.txt"
    f.write_text("file-backed doc", encoding="utf-8")
    doc_file = Document(
        company_id="C1", workplace_id="W1", domain="policy", owner_id=bot.id,
        is_compliance_source=False, title="파일문서", file_name="rule.txt",
        file_path=str(f), source_name="파일문서", embedding_status="COMPLETED",
    )
    db.add(doc_file)
    db.commit()
    db.refresh(doc_file)
    return bot, doc_vec, doc_file, f


def test_cleanup_happy_path_and_idempotent(db, vs, tmp_path):
    bot, doc_vec, doc_file, f = _make_bot_with_docs(db, vs, tmp_path)
    bot_id, dv_id, df_id = bot.id, doc_vec.id, doc_file.id

    assert vs.client.count(COLLECTION_NAME).count >= 1  # 벡터 적재됨

    # 봇 Soft Delete -> cascade: 소속 문서 모두 DELETING
    BotService(db).soft_delete_bot(bot_id, TENANT)
    assert db.get(Bot, bot_id).status == "DELETING"
    assert db.get(Document, dv_id).embedding_status == "DELETING"
    assert db.get(Document, df_id).embedding_status == "DELETING"

    # 물리 정리
    result = run_cleanup(db, vector_store=vs)
    assert result["documents_deleted"] == 2
    assert result["documents_failed"] == 0
    assert result["bots_deleted"] == 1

    # 벡터/파일/행 모두 제거
    assert vs.client.count(COLLECTION_NAME).count == 0
    assert db.get(Document, dv_id) is None
    assert db.get(Document, df_id) is None
    assert db.get(Bot, bot_id) is None
    assert not f.exists()

    # 멱등: 재실행해도 0건, 무에러
    again = run_cleanup(db, vector_store=vs)
    assert again == {
        "documents_deleted": 0, "documents_failed": 0,
        "bots_deleted": 0, "bots_pending": 0,
    }


def test_cleanup_qdrant_failure_keeps_deleting_then_retries(db, vs, tmp_path):
    bot, doc_vec, doc_file, f = _make_bot_with_docs(db, vs, tmp_path)
    bot_id, dv_id = bot.id, doc_vec.id
    BotService(db).soft_delete_bot(bot_id, TENANT)

    # 1) Qdrant 장애 -> 문서 물리삭제 실패, 롤백으로 행 보존(DELETING 유지), 봇은 잔여문서로 보류
    failing = _FailingVS(COLLECTION_NAME)
    result = run_cleanup(db, vector_store=failing)
    assert result["documents_failed"] == 2
    assert result["documents_deleted"] == 0
    assert result["bots_deleted"] == 0
    assert result["bots_pending"] == 1  # 잔여 문서 있어 봇 삭제 보류

    # 행 그대로 + DELETING 유지(좀비벡터 방지 — 부분삭제 없음)
    assert db.get(Document, dv_id) is not None
    assert db.get(Document, dv_id).embedding_status == "DELETING"
    assert db.get(Bot, bot_id) is not None
    # 벡터도 그대로(삭제 시도가 예외로 무위 -> 다음 주기 재시도 대상)
    assert vs.client.count(COLLECTION_NAME).count >= 1

    # 2) 복구 후 재시도 -> 결국 정리(eventual consistency)
    result2 = run_cleanup(db, vector_store=vs)
    assert result2["documents_deleted"] == 2
    assert result2["bots_deleted"] == 1
    assert vs.client.count(COLLECTION_NAME).count == 0
    assert db.get(Bot, bot_id) is None
    assert not f.exists()
