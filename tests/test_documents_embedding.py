"""공통 Documents 비동기 임베딩 파이프라인 검증 (Phase B, Step 4).

업로드 → FastAPI BackgroundTask(파일 파싱 → 청킹 → 임베딩 → Qdrant 적재 → DB COMPLETED)
까지 end-to-end 로 증명한다. 외부 비용/네트워크 제거: in-memory SQLite + in-memory Qdrant +
DeterministicFakeEmbedding(가짜 임베딩). 백그라운드 태스크가 테스트 DB/스토어/업로드 경로를
쓰도록 document_service 모듈 전역(SessionLocal, get_policy_vector_store, UPLOAD_BASE_DIR)을
monkeypatch 한다.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client import models as qmodels
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.services.document_service as docsvc
from app.ai.vector_store import COLLECTION_NAME
from app.db.session import get_db
from app.main import app
from app.models import Base
from app.models.documents import Document

_DIM = 256
_HEADERS = {"X-Company-ID": "C1", "X-Workplace-ID": "W1"}


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(eng)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def fake_vector_store():
    """in-memory Qdrant(tenant_documents) + 결정론적 가짜 임베딩."""
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
def client(engine, fake_vector_store, monkeypatch, tmp_path):
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    # 백그라운드 태스크는 요청 세션 밖에서 자체 SessionLocal()/공용 스토어를 쓰므로
    # 모듈 전역을 테스트용으로 교체해야 같은 in-memory DB/Qdrant 를 본다.
    monkeypatch.setattr(docsvc, "SessionLocal", factory)
    monkeypatch.setattr(docsvc, "get_policy_vector_store", lambda: fake_vector_store)
    monkeypatch.setattr(docsvc, "UPLOAD_BASE_DIR", str(tmp_path))

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c, factory, fake_vector_store
    app.dependency_overrides.clear()


def test_upload_triggers_async_embedding_to_completed(client):
    """업로드 → 백그라운드 임베딩 → DB COMPLETED + Qdrant 적재(메타데이터 포함)."""
    c, factory, vs = client
    # 500자 초과 텍스트 -> 다중 청크로 분할되는지까지 확인.
    text = "회사 식대 규정: 1인 1만5천원 한도이며 초과 시 사유서를 제출해야 합니다. " * 30

    resp = c.post(
        "/api/v1/documents/upload",
        headers=_HEADERS,
        data={
            "title": "식대규정",
            "owner_id": "owner-x",
            "domain": "policy",
            "is_compliance_source": "false",
        },
        files={"file": ("rule.txt", text.encode("utf-8"), "text/plain")},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["success"] is True
    doc_id = body["data"]["id"]

    # 백그라운드 완료 후 DB 최종 상태 = COMPLETED (TestClient 는 응답 후 백그라운드를 동기 실행)
    with factory() as db:
        doc = db.get(Document, doc_id)
        assert doc is not None
        final_status = doc.embedding_status
        chunk_count = doc.chunk_count
        err = doc.error_message
    assert final_status == "COMPLETED", f"status={final_status} err={err}"
    assert chunk_count >= 2, f"청킹이 다중 청크여야 함: {chunk_count}"

    # Qdrant 적재 확인 — 포인트 수 == chunk_count
    qc = vs.client
    assert qc.count(COLLECTION_NAME).count == chunk_count

    # ⚠️ 메타데이터 페이로드 검증(격리/필터 필드 필수: 설계 §3, Rule #1·#2)
    points, _ = qc.scroll(COLLECTION_NAME, limit=1, with_payload=True)
    meta = points[0].payload["metadata"]
    assert meta["company_id"] == "C1"
    assert meta["workplace_id"] == "W1"
    assert meta["domain"] == "policy"
    assert meta["is_compliance_source"] is False
    assert meta["owner_id"] == "owner-x"
    assert meta["doc_id"] == doc_id
    assert meta["source"] == "식대규정"
    assert "chunk_index" in meta


def test_ingest_text_sync_embedding_completed(engine, fake_vector_store):
    """텍스트 즉시 적재(동기) → 생성 즉시 COMPLETED + 컴플라이언스 메타데이터(expense_rule) 적재."""
    from app.core.dependencies import TenantContext
    from app.schemas.documents import DocumentIngestTextRequest

    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    tenant = TenantContext(company_id="C1", workplace_id="W1")
    with factory() as db:
        service = docsvc.DocumentService(db, vector_store=fake_vector_store)
        doc = service.ingest_text(
            tenant,
            DocumentIngestTextRequest(
                text="경비 지출 사칙: 접대비는 건당 30만원 한도. " * 20,
                source_name="경비사칙",
                owner_id=None,  # 컴플라이언스 기준 문서는 owner 미지정 가능(§8)
                domain="expense_rule",
                is_compliance_source=True,
            ),
        )
        assert doc.embedding_status == "COMPLETED", doc.error_message
        assert doc.chunk_count >= 1

    # 컴플라이언스 이중게이트 필드가 payload 에 그대로 적재되었는지(domain+flag)
    qc = fake_vector_store.client
    points, _ = qc.scroll(COLLECTION_NAME, limit=1, with_payload=True)
    meta = points[0].payload["metadata"]
    assert meta["domain"] == "expense_rule"
    assert meta["is_compliance_source"] is True
    assert meta["doc_id"] == doc.id
