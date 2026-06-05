"""사내 규정 RAG 서비스 (11단계 + 12단계 컴플라이언스).

세 가지 책임:
    * ingest_policy_text : 규정 원문을 청크로 분할하고, 반드시 테넌트 식별자
      (company_id / workplace_id) 를 메타데이터에 주입하여 Qdrant 에 적재.
    * ask_policy         : 질문을 받아 **현재 테넌트와 일치하는 청크만**
      Payload Filter 로 검색하고, 그 문맥만 근거로 LLM 답변을 생성.
    * check_compliance   : (12단계) 결제 1건이 현재 테넌트의 사칙에 위배되는지
      RAG 로 판정. LangGraph 의 compliance_node 가 호출한다.

멀티테넌트 격리의 책임은 전적으로 이 서비스의 Payload Filter 에 있다. 다른
테넌트의 규정은 애초에 검색 결과로 나오지 않으므로 LLM 프롬프트에 유입되지 않는다.
"""
from __future__ import annotations

import logging
import os

from langchain_core.prompts import ChatPromptTemplate
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel, Field
from qdrant_client import models

from app.ai.vector_store import get_policy_vector_store
from app.core.config import settings
from app.core.dependencies import TenantContext
from app.schemas.transactions import SingleTransactionTestRequest

logger = logging.getLogger(__name__)

# 검색된 문맥이 전혀 없을 때(=타 테넌트이거나 미적재) 돌려줄 고정 답변.
# 멀티테넌트 격리 시 '모른다' 뉘앙스를 LLM 환각 없이 결정론적으로 보장한다.
_NO_CONTEXT_ANSWER = "관련된 사내 규정을 찾을 수 없습니다."

_SYSTEM_PROMPT = """당신은 회사의 사내 규정을 안내하는 도우미입니다.
반드시 아래에 주어지는 '참고 문맥' 에 적힌 내용만 근거로 답변하세요.
문맥에 답이 없으면 추측하지 말고 정확히 "관련된 사내 규정을 찾을 수 없습니다." 라고만 답하세요."""

_HUMAN_TEMPLATE = """참고 문맥:
{context}

질문: {question}

위 '참고 문맥' 만 근거로 한국어로 간결하게 답변하세요."""

# --- 컴플라이언스 판정용 프롬프트 (12단계) ---
_COMPLIANCE_SYSTEM_PROMPT = """당신은 회사의 사내 규정 준수 여부를 판정하는 컴플라이언스 감사관입니다.
반드시 아래 '참고 문맥'(사내 규정)에 적힌 내용만 근거로 판정하세요.
- 결제가 사칙에 명백히 위배되면 is_compliant=False 로 하고, reason 에 위배 사유를
  구체적으로(어떤 규정의 어떤 한도·조건을 어겼는지) 한국어로 적으세요.
- 위배 근거가 문맥에 없거나 규정을 준수하면 is_compliant=True 로 하고 reason 은 비워 두세요."""

_COMPLIANCE_HUMAN_TEMPLATE = """참고 문맥(사내 규정):
{context}

{question}"""


class ComplianceResult(BaseModel):
    """LLM 컴플라이언스 판정 정형 출력 (with_structured_output 대상)."""

    is_compliant: bool = Field(
        ...,
        description="제공된 사칙 문맥에 비추어 결제가 규정을 준수하면 True, 위배되면 False",
    )
    reason: str = Field(
        ...,
        description="위배 사유. 위배가 아니면 빈 문자열.",
    )


def build_policy_llm():
    """규정 답변 생성용 ChatOpenAI 구성.

    `llm_recommender.py` 와 동일한 정책: 커스텀 base_url(`OPENAI_API_BASE`) 적용 +
    사내 CA(`SSL_CERT_FILE`) 가 있으면 verify=<CA> 로 http_client 주입.
    """
    from langchain_openai import ChatOpenAI

    llm_kwargs: dict = {
        "api_key": settings.OPENAI_API_KEY,
        "base_url": settings.OPENAI_API_BASE,
        "model": settings.LLM_MODEL,
        "temperature": 0,
    }

    ssl_cert = os.environ.get("SSL_CERT_FILE")
    if ssl_cert and os.path.isfile(ssl_cert):
        import httpx

        llm_kwargs["http_client"] = httpx.Client(
            verify=ssl_cert, timeout=settings.llm_http_timeout
        )

    return ChatOpenAI(**llm_kwargs)


class PolicyService:
    """사내 규정 RAG 도메인 서비스.

    vector_store / llm 은 DI 가능하다(테스트 시 in-memory Qdrant·대체 LLM 주입).
    기본값은 운영용 Qdrant(`get_policy_vector_store`) 와 ChatOpenAI 이며, 둘 다
    실제 외부 의존성을 잡으므로 인자를 넘기지 않으면 첫 사용 시점에 연결된다.
    """

    # 청크 분할 파라미터. 규정 문서 특성상 과도하게 쪼개지 않도록 보수적으로 설정.
    _CHUNK_SIZE = 500
    _CHUNK_OVERLAP = 50

    def __init__(
        self,
        vector_store: QdrantVectorStore | None = None,
        llm=None,
    ) -> None:
        # I/O(임베딩 연결/컬렉션 보장)를 __init__ 에서 하지 않도록 lazy 초기화한다.
        # 주입된 인스턴스가 있으면 그대로 쓰고, 없으면 첫 사용 시점에 운영 기본값을 만든다.
        # -> TransactionService 가 PolicyService() 를 기본 생성해도 임베딩 서버에 즉시
        #    연결하지 않으므로, 매칭 결과가 있어 실제 compliance 를 탈 때만 연결된다.
        self._vector_store = vector_store
        self._llm = llm

    @property
    def vector_store(self) -> QdrantVectorStore:
        if self._vector_store is None:
            self._vector_store = get_policy_vector_store()
        return self._vector_store

    @property
    def llm(self):
        if self._llm is None:
            self._llm = build_policy_llm()
        return self._llm

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _tenant_conditions(tenant: TenantContext) -> list[models.FieldCondition]:
        """테넌트 격리 공통 조건(company_id AND workplace_id)."""
        return [
            models.FieldCondition(
                key="metadata.company_id",
                match=models.MatchValue(value=tenant.company_id),
            ),
            models.FieldCondition(
                key="metadata.workplace_id",
                match=models.MatchValue(value=tenant.workplace_id),
            ),
        ]

    @staticmethod
    def _tenant_filter(tenant: TenantContext) -> models.Filter:
        """현재 테넌트(company_id AND workplace_id)로 격리하는 Qdrant Payload Filter.

        (하위호환 유지 — 테스트 더블 등에서 사용. 신규 경로는 도메인별 필터를 쓴다.)
        """
        return models.Filter(must=PolicyService._tenant_conditions(tenant))

    @staticmethod
    def _policy_filter(tenant: TenantContext) -> models.Filter:
        """챗봇 일반 규정 검색용: 테넌트 + domain="policy" (설계 §8 일관화)."""
        return models.Filter(
            must=[
                *PolicyService._tenant_conditions(tenant),
                models.FieldCondition(
                    key="metadata.domain", match=models.MatchValue(value="policy")
                ),
            ]
        )

    @staticmethod
    def _compliance_filter(tenant: TenantContext) -> models.Filter:
        """영수증 컴플라이언스 검색용 — **이중 게이트**(Critical Design Rule #1, 설계 §8):
        테넌트 + domain="expense_rule" AND is_compliance_source=true.

        일반 규정(domain="policy")이 컴플라이언스 컨텍스트에 섞여 환각을 일으키는 것을 원천 차단.
        """
        return models.Filter(
            must=[
                *PolicyService._tenant_conditions(tenant),
                models.FieldCondition(
                    key="metadata.domain",
                    match=models.MatchValue(value="expense_rule"),
                ),
                models.FieldCondition(
                    key="metadata.is_compliance_source",
                    match=models.MatchValue(value=True),
                ),
            ]
        )

    # ------------------------------------------------------------------ #
    # Ingest
    # ------------------------------------------------------------------ #
    def ingest_policy_text(
        self,
        text: str,
        source_name: str,
        tenant: TenantContext,
    ) -> int:
        """규정 텍스트를 청크로 분할 후, 테넌트 메타데이터를 주입해 Qdrant 에 적재.

        **반드시** 각 청크 메타데이터에 `company_id` / `workplace_id` 를 주입한다.
        이 값이 곧 `ask_policy` 의 격리 검색 키가 된다. 반환값은 적재된 청크 수.
        """
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self._CHUNK_SIZE,
            chunk_overlap=self._CHUNK_OVERLAP,
        )
        chunks = splitter.split_text(text)

        metadatas = [
            {
                "company_id": tenant.company_id,
                "workplace_id": tenant.workplace_id,
                "domain": "policy",  # 챗봇 일반 규정 도메인(§8 일관화)
                "source": source_name,
            }
            for _ in chunks
        ]

        self.vector_store.add_texts(texts=chunks, metadatas=metadatas)
        logger.info(
            "규정 적재 완료: source=%s tenant=%s/%s chunks=%d",
            source_name,
            tenant.company_id,
            tenant.workplace_id,
            len(chunks),
        )
        return len(chunks)

    # ------------------------------------------------------------------ #
    # Ask (RAG)
    # ------------------------------------------------------------------ #
    def ask_policy(self, query: str, tenant: TenantContext) -> str:
        """질문에 대해 현재 테넌트 범위로 격리된 RAG 답변을 생성한다.

        흐름:
            1) `metadata.company_id` AND `metadata.workplace_id` 가 모두 일치하는
               청크만 Qdrant Payload Filter 로 검색 (타 테넌트 데이터 원천 차단).
            2) 검색 결과가 없으면 LLM 호출 없이 '모른다' 고정 답변 반환(격리 보장).
            3) 있으면 그 문맥만 프롬프트에 넣어 ChatOpenAI 로 답변 생성.
        """
        docs = self.vector_store.similarity_search(
            query, k=4, filter=self._policy_filter(tenant)
        )
        if not docs:
            logger.info(
                "규정 검색 결과 없음: tenant=%s/%s query=%r",
                tenant.company_id,
                tenant.workplace_id,
                query,
            )
            return _NO_CONTEXT_ANSWER

        context = "\n\n".join(doc.page_content for doc in docs)
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", _SYSTEM_PROMPT),
                ("human", _HUMAN_TEMPLATE),
            ]
        )
        chain = prompt | self.llm
        response = chain.invoke({"context": context, "question": query})
        return response.content

    # ------------------------------------------------------------------ #
    # Compliance check (12단계)
    # ------------------------------------------------------------------ #
    def check_compliance(
        self,
        payload: SingleTransactionTestRequest,
        category_name: str,
        tenant: TenantContext,
    ) -> dict:
        """결제 1건이 현재 테넌트의 사칙에 위배되는지 RAG 로 판정한다.

        흐름:
            1) 11단계 격리 검색 로직 재활용 -- 현재 테넌트의 사칙 청크만 검색.
            2) 검색 결과가 없으면 판단 근거가 없으므로 준수로 간주
               -> {"is_compliant": True, "reason": None}.
            3) 있으면 문맥을 프롬프트에 넣어 with_structured_output 으로
               ComplianceResult 를 받아 dict 로 변환해 반환.

        반환: {"is_compliant": bool, "reason": str | None}
        """
        docs = self.vector_store.similarity_search(
            f"{category_name} 사용 한도 및 사칙 규정",
            k=4,
            filter=self._compliance_filter(tenant),  # 이중 게이트(§8, Rule #1)
        )
        if not docs:
            return {"is_compliant": True, "reason": None}

        context = "\n\n".join(doc.page_content for doc in docs)
        question = (
            f"사용자가 {payload.merchant_name}에서 {payload.amount}원을 "
            f"{category_name} 용도로 사용하려 합니다. 제공된 사칙 문맥에 비추어 "
            f"보았을 때 이 결제가 사칙에 위배되나요?"
        )
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", _COMPLIANCE_SYSTEM_PROMPT),
                ("human", _COMPLIANCE_HUMAN_TEMPLATE),
            ]
        )
        structured_llm = self.llm.with_structured_output(ComplianceResult)
        result: ComplianceResult = (prompt | structured_llm).invoke(
            {"context": context, "question": question}
        )
        logger.info(
            "컴플라이언스 판정: tenant=%s/%s merchant=%s amount=%d category=%s -> compliant=%s",
            tenant.company_id,
            tenant.workplace_id,
            payload.merchant_name,
            payload.amount,
            category_name,
            result.is_compliant,
        )
        return {
            "is_compliant": result.is_compliant,
            "reason": result.reason if not result.is_compliant else None,
        }
