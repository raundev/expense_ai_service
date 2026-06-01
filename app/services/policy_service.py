"""사내 규정 RAG 서비스 (11단계).

두 가지 책임:
    * ingest_policy_text : 규정 원문을 청크로 분할하고, 반드시 테넌트 식별자
      (company_id / workplace_id) 를 메타데이터에 주입하여 Qdrant 에 적재.
    * ask_policy         : 질문을 받아 **현재 테넌트와 일치하는 청크만**
      Payload Filter 로 검색하고, 그 문맥만 근거로 LLM 답변을 생성.

멀티테넌트 격리의 책임은 전적으로 이 서비스의 Payload Filter 에 있다. 다른
테넌트의 규정은 애초에 검색 결과로 나오지 않으므로 LLM 프롬프트에 유입되지 않는다.

다음 12단계에서 이 `ask_policy` 엔진이 LangGraph 추천 파이프라인의
'컴플라이언스 위반 검증 노드' 로 결합된다.
"""
from __future__ import annotations

import logging
import os

from langchain_core.prompts import ChatPromptTemplate
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import models

from app.ai.vector_store import get_policy_vector_store
from app.core.config import settings
from app.core.dependencies import TenantContext

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

        llm_kwargs["http_client"] = httpx.Client(verify=ssl_cert, timeout=60.0)

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
        self.vector_store = (
            vector_store if vector_store is not None else get_policy_vector_store()
        )
        self.llm = llm if llm is not None else build_policy_llm()

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
        tenant_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="metadata.company_id",
                    match=models.MatchValue(value=tenant.company_id),
                ),
                models.FieldCondition(
                    key="metadata.workplace_id",
                    match=models.MatchValue(value=tenant.workplace_id),
                ),
            ]
        )

        docs = self.vector_store.similarity_search(query, k=4, filter=tenant_filter)
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
