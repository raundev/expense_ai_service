"""pytest 공용 픽스처.

병합 노트: 두 테스트 스위트의 픽스처를 합쳐 둔 파일이다(이름 충돌 없음).
- (LLM/그래프 단위 테스트) 프로젝트 루트를 sys.path 에 넣어 `app` 패키지를 어디서
  실행하든 import 가능하게 하고, 인메모리 SQLite 세션(StaticPool)으로 DB 의존 노드/
  서비스를 격리 테스트한다. LLM/RAG 외부 의존성은 Fake 로 대체한다.
- (컴플라이언스 통합 테스트, 16단계) 인메모리 SQLite(StaticPool) 기반 테스트 DB +
  FastAPI TestClient 픽스처. 외부 비용/종속성 제거: 임베딩은 FakeEmbedding +
  in-memory Qdrant(실제 검색/격리 동작), LLM 판정은 결정론적 스텁으로 대체
  (RunPod/OpenAI 호출 없음).
"""
from __future__ import annotations

import os
import sys
from datetime import date

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client import models as qmodels
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# pytest 가 tests/ 만 sys.path 에 넣어도 app 패키지를 찾도록 프로젝트 루트를 추가.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.endpoints.policies import get_policy_service  # noqa: E402
from app.api.endpoints.transactions import get_transaction_service  # noqa: E402
from app.core.dependencies import TenantContext  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.schemas.transactions import SingleTransactionTestRequest  # noqa: E402
from app.services.policy_service import PolicyService  # noqa: E402
from app.services.transaction_service import TransactionService  # noqa: E402

EMBED_DIM = 1536

# 테스트 공용 멀티테넌트 헤더
HEADERS_A = {"X-Company-ID": "COMPANY_A", "X-Workplace-ID": "HQ"}
HEADERS_A_ADMIN = {**HEADERS_A, "X-Admin-ID": "admin_kim"}
HEADERS_B = {"X-Company-ID": "COMPANY_B", "X-Workplace-ID": "HQ"}


class FakeRecommender:
    """ReceiptLLMRecommender 대체. 고정 LLMSelection(또는 None)을 반환하고 받은 후보를 기록."""

    def __init__(self, result):
        self.result = result
        self.seen_candidates = None

    def select(self, payload, candidates):
        self.seen_candidates = list(candidates)
        return self.result


class FakePolicy:
    """PolicyService.check_compliance 대체. 고정 판정을 반환하고 호출 여부를 기록."""

    def __init__(self, is_compliant: bool = True, reason: str | None = None):
        self._verdict = {"is_compliant": is_compliant, "reason": reason}
        self.called = False

    def check_compliance(self, payload, category_name, tenant):  # noqa: ARG002
        self.called = True
        return dict(self._verdict)


class MockPolicyService(PolicyService):
    """테스트 더블.

    임베딩/벡터 검색은 실제(FakeEmbedding + in-memory Qdrant)로 동작시켜 테넌트 격리
    Payload Filter 경로를 그대로 검증하고, **LLM 판정만** 결정론적으로 대체한다
    (식대 한도 15,000원 초과 시 위반). 외부 LLM 호출이 전혀 없다.
    """

    def ask_policy(self, query: str, tenant) -> str:  # type: ignore[override]
        docs = self.vector_store.similarity_search(
            query, k=4, filter=self._tenant_filter(tenant)
        )
        if not docs:
            return "관련된 사내 규정을 찾을 수 없습니다."
        return docs[0].page_content

    def check_compliance(self, payload, category_name, tenant) -> dict:  # type: ignore[override]
        docs = self.vector_store.similarity_search(
            f"{category_name} 한도", k=4, filter=self._tenant_filter(tenant)
        )
        if not docs:
            return {"is_compliant": True, "reason": None}
        if payload.amount > 15000:
            return {
                "is_compliant": False,
                "reason": f"한도 15,000원 초과 ({payload.amount}원)",
            }
        return {"is_compliant": True, "reason": None}


# ---------------------------------------------------------------------------
# LLM/그래프 단위 테스트용 픽스처 (main 계열)
# ---------------------------------------------------------------------------
@pytest.fixture
def db_session():
    """인메모리 SQLite 세션. 모델 메타데이터로 테이블을 생성하므로 신규 컬럼도 자동 반영."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def tenant() -> TenantContext:
    return TenantContext(company_id="C1", workplace_id="W1")


@pytest.fixture
def payload_factory():
    """SingleTransactionTestRequest 생성 팩토리. overrides 로 필드 교체."""

    def _make(**overrides) -> SingleTransactionTestRequest:
        data = dict(
            receipt_date=date(2026, 6, 4),
            receipt_time="12:30",
            merchant_name="스타벅스 강남점",
            merchant_sector_code=None,
            amount=15000,
        )
        data.update(overrides)
        return SingleTransactionTestRequest(**data)

    return _make


@pytest.fixture
def make_recommender():
    return FakeRecommender


@pytest.fixture
def make_policy():
    return FakePolicy


# ---------------------------------------------------------------------------
# 컴플라이언스 통합 테스트용 픽스처 (feature/rag_compliance 계열)
# ---------------------------------------------------------------------------
@pytest.fixture
def session_factory():
    """인메모리 SQLite 엔진 + 전체 스키마(create_all). 테스트마다 새로 생성."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture
def mock_policy_service() -> MockPolicyService:
    """FakeEmbedding + in-memory Qdrant 로 구성한 테스트 PolicyService."""
    qc = QdrantClient(location=":memory:")
    qc.create_collection(
        collection_name="company_policies",
        vectors_config=qmodels.VectorParams(size=EMBED_DIM, distance=qmodels.Distance.COSINE),
    )
    vs = QdrantVectorStore(
        client=qc,
        collection_name="company_policies",
        embedding=DeterministicFakeEmbedding(size=EMBED_DIM),
    )
    return MockPolicyService(vector_store=vs)


@pytest.fixture
def client(session_factory, mock_policy_service) -> TestClient:
    """의존성 오버라이드(테스트 DB + Mock PolicyService)가 적용된 TestClient."""

    def _get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    def _get_txn_service(db: Session = Depends(get_db)) -> TransactionService:
        return TransactionService(db, policy_service=mock_policy_service)

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_transaction_service] = _get_txn_service
    app.dependency_overrides[get_policy_service] = lambda: mock_policy_service

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
