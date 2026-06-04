"""pytest 공용 픽스처.

- 프로젝트 루트를 sys.path 에 넣어 `app` 패키지를 어디서 실행하든 import 가능하게 한다.
- 인메모리 SQLite 세션(StaticPool 로 단일 커넥션 유지)으로 DB 의존 노드/서비스를 격리 테스트한다.
- LLM/RAG 외부 의존성은 Fake 로 대체한다(네트워크/Qdrant/LLM 호출 없음).
"""
from __future__ import annotations

import os
import sys
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

# pytest 가 tests/ 만 sys.path 에 넣어도 app 패키지를 찾도록 프로젝트 루트를 추가.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.dependencies import TenantContext  # noqa: E402
from app.models import Base  # noqa: E402
from app.schemas.transactions import SingleTransactionTestRequest  # noqa: E402


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
