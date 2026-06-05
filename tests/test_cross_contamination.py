"""교차 오염 방지(Cross-Contamination) 검증 — Phase C 필터 + §8 컴플라이언스 이중게이트.

단일 테넌트 내 2개 문서:
  - 문서 A: domain="policy",       owner_id=bot.id,        is_compliance_source=False  ("카페테리아 메뉴")
  - 문서 B: domain="expense_rule", owner_id="compliance-sys", is_compliance_source=True ("식대 결제 한도 2만원")

검증 1: 챗봇(Bot-1) /chat 검색은 domain=policy+owner_id=bot 만 보므로 문서 B 가 sources 에 없다.
검증 2: 컴플라이언스 검색은 domain=expense_rule+is_compliance_source 만 보므로 문서 A 가 컨텍스트에 없다.

외부 LLM/네트워크 제거: in-memory SQLite + in-memory Qdrant + DeterministicFakeEmbedding + Fake LLM.
필터(격리)가 핵심이므로 LLM 은 고정 응답/컨텍스트 캡처용 더블을 주입한다.
"""
from __future__ import annotations

from datetime import date

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client import models as qmodels
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.vector_store import COLLECTION_NAME
from app.core.dependencies import TenantContext
from app.models import Base
from app.schemas.bots import BotCreateRequest
from app.schemas.documents import DocumentIngestTextRequest
from app.schemas.policies import PolicyChatRequest
from app.schemas.transactions import SingleTransactionTestRequest
from app.services.bot_service import BotService
from app.services.chat_service import ChatService
from app.services.document_service import DocumentService
from app.services.policy_service import PolicyService

_DIM = 256
TENANT = TenantContext(company_id="C1", workplace_id="W1")

DOC_A_TEXT = "사내 카페테리아 메뉴 안내. 본관 3층 카페테리아 운영시간은 오전 8시부터 오후 7시까지입니다. 점심 메뉴는 매일 변경됩니다."
DOC_B_TEXT = "식대 결제 한도 규정. 1인 식대는 2만원을 초과할 수 없습니다. 초과 결제는 사칙 위반으로 처리됩니다."


class _FakeChatLLM:
    """ChatService 주입용. invoke -> 고정 답변, with_structured_output -> RETRIEVE 의도."""

    def __init__(self, answer: str = "테스트 답변입니다."):
        self._answer = answer

    def invoke(self, _input):
        return AIMessage(content=self._answer)

    def with_structured_output(self, schema):
        return RunnableLambda(lambda _x: schema(intent="RETRIEVE"))


class _CaptureComplianceLLM:
    """PolicyService 주입용. check_compliance 가 LLM 에 넘긴 '참고 문맥'을 캡처한다."""

    def __init__(self, is_compliant: bool = True, reason: str = ""):
        self.captured: list[str] = []
        self._ic, self._reason = is_compliant, reason

    def with_structured_output(self, schema):
        def _run(prompt_value):
            text = (
                prompt_value.to_string()
                if hasattr(prompt_value, "to_string")
                else str(prompt_value)
            )
            self.captured.append(text)
            return schema(is_compliant=self._ic, reason=self._reason)

        return RunnableLambda(_run)


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


@pytest.fixture
def seeded(db, vs):
    """Bot-1(활성) + 문서 A(policy/bot) + 문서 B(expense_rule/compliance) 적재."""
    bot = BotService(db).create_bot(BotCreateRequest(name="Bot-1"), TENANT)
    BotService(db).set_disabled(bot.id, TENANT, disabled=False)

    docsvc = DocumentService(db, vector_store=vs)
    doc_a = docsvc.ingest_text(
        TENANT,
        DocumentIngestTextRequest(
            text=DOC_A_TEXT, source_name="카페테리아안내",
            owner_id=bot.id, domain="policy", is_compliance_source=False,
        ),
    )
    doc_b = docsvc.ingest_text(
        TENANT,
        DocumentIngestTextRequest(
            text=DOC_B_TEXT, source_name="식대규정",
            owner_id="compliance-sys", domain="expense_rule", is_compliance_source=True,
        ),
    )
    assert doc_a.embedding_status == "COMPLETED"
    assert doc_b.embedding_status == "COMPLETED"
    return bot, doc_a, doc_b


def test_chat_does_not_retrieve_compliance_doc(db, vs, seeded):
    """검증 1: 챗봇 검색에 컴플라이언스 전용 문서 B 가 절대 딸려오지 않는다."""
    bot, doc_a, doc_b = seeded
    chat = ChatService(db, vector_store=vs, llm=_FakeChatLLM())
    result = chat.chat(TENANT, PolicyChatRequest(bot_id=bot.id, query="식대 한도가 얼마야?"))

    source_ids = {s.doc_id for s in result["sources"]}
    assert doc_b.id not in source_ids, "컴플라이언스 문서 B 가 챗봇 검색에 오염됨!"
    assert doc_a.id in source_ids, "봇 소유 policy 문서 A 는 검색되어야 함"


def test_compliance_does_not_retrieve_policy_doc(db, vs, seeded):
    """검증 2: 컴플라이언스 검색 컨텍스트에 일반 챗봇 문서 A 가 절대 포함되지 않는다."""
    bot, doc_a, doc_b = seeded
    capture = _CaptureComplianceLLM(is_compliant=True, reason="")
    ps = PolicyService(vector_store=vs, llm=capture)

    payload = SingleTransactionTestRequest(
        receipt_date=date(2026, 6, 5), receipt_time="12:00",
        merchant_name="식당", merchant_sector_code=None, amount=25000,
    )
    ps.check_compliance(payload, category_name="식대", tenant=TENANT)

    assert capture.captured, "컴플라이언스 문서가 검색되어 LLM 이 호출되어야 함"
    ctx = capture.captured[0]
    assert "카페테리아" not in ctx, "일반 policy 문서 A 가 컴플라이언스 컨텍스트에 오염됨!"
    assert ("2만원" in ctx or "식대 결제 한도" in ctx), "컴플라이언스 기준 문서 B 가 컨텍스트에 있어야 함"
