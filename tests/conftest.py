"""pytest 공용 픽스처 (16단계).

- 인메모리 SQLite(StaticPool) 기반 테스트 DB + FastAPI TestClient 픽스처
- 외부 비용/종속성 제거: 임베딩은 FakeEmbedding + in-memory Qdrant(실제 검색/격리 동작),
  LLM 판정은 결정론적 스텁으로 대체 (RunPod/OpenAI 호출 없음)
"""
from __future__ import annotations

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

from app.api.endpoints.policies import get_policy_service
from app.api.endpoints.transactions import get_transaction_service
from app.db.session import get_db
from app.main import app
from app.models import Base
from app.services.policy_service import PolicyService
from app.services.transaction_service import TransactionService

EMBED_DIM = 1536

# 테스트 공용 멀티테넌트 헤더
HEADERS_A = {"X-Company-ID": "COMPANY_A", "X-Workplace-ID": "HQ"}
HEADERS_A_ADMIN = {**HEADERS_A, "X-Admin-ID": "admin_kim"}
HEADERS_B = {"X-Company-ID": "COMPANY_B", "X-Workplace-ID": "HQ"}


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
