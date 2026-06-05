"""Policy RAG 챗봇 — chat 8단계 파이프라인 서비스 (설계 §5.2).

검색은 **봇 전용 문서만** 타겟한다: company_id + workplace_id + domain="policy" +
owner_id=bot_id (Critical Design Rule #1·#5 — 테넌트/봇 격리). 의도분류(LLM)가
HISTORY_ONLY 로 판단해도, 세션에 RAG 출처(sources) 컨텍스트가 단 하나도 없으면 강제로
RETRIEVE 로 폴백한다(Rule #3 — 검색 없이 LLM 이 규정을 지어내는 환각 차단).

테스트 용이성: vector_store / llm 은 생성자 주입 가능(없으면 운영 기본값 lazy 구성).
"""
from __future__ import annotations

import json
import logging
import os

from qdrant_client import models as qmodels
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.vector_store import get_policy_vector_store
from app.core.config import settings
from app.core.dependencies import TenantContext
from app.models.bots import Bot
from app.models.chat import ChatMessage, ChatSession
from app.models.documents import Document
from app.schemas.chat import ChatHistoryResponse, ChatMessageResponse, ChatSource
from app.schemas.policies import PolicyChatRequest
from app.services.bot_service import STATUS_DELETING, BotDisabledError, BotNotFoundError
from app.services.policy_service import _NO_CONTEXT_ANSWER
from app.services.query_reformulation import (
    Intent,
    classify_intent,
    needs_reformulation,
    reformulate_query,
)

logger = logging.getLogger(__name__)

_MAX_MSG_CHARS = 4000  # 히스토리 메시지당 절단(설계 §5.2-3)
_SNIPPET_MAX = 300  # sources snippet 최대 길이(설계 §5.1)

_DEFAULT_SYSTEM_PROMPT = """당신은 회사의 사내 규정을 안내하는 도우미입니다.
반드시 아래에 주어지는 '참고 문맥' 에 적힌 내용만 근거로 답변하세요.
문맥에 답이 없으면 추측하지 말고 정확히 "관련된 사내 규정을 찾을 수 없습니다." 라고만 답하세요."""

_HISTORY_ONLY_SYSTEM = """당신은 회사 규정 챗봇입니다. 아래 '이전 대화' 의 내용만 근거로
사용자의 요청(요약/번역/형식변환 등)을 수행하세요. 이전 대화에 없는 새로운 사실을 지어내지 마세요."""


def build_chat_llm(*, model: str, temperature: float, max_tokens: int | None = None):
    """봇 설정(model/temperature/max_tokens)으로 ChatOpenAI 구성.

    policy_service.build_policy_llm 과 동일한 사내 base_url(`OPENAI_API_BASE`)/SSL CA
    (`SSL_CERT_FILE`) 정책을 적용한다.
    """
    from langchain_openai import ChatOpenAI

    kwargs: dict = {
        "api_key": settings.OPENAI_API_KEY,
        "base_url": settings.OPENAI_API_BASE,
        "model": model,
        "temperature": temperature,
    }
    if max_tokens:
        kwargs["max_tokens"] = max_tokens

    ssl_cert = os.environ.get("SSL_CERT_FILE")
    if ssl_cert and os.path.isfile(ssl_cert):
        import httpx

        kwargs["http_client"] = httpx.Client(
            verify=ssl_cert, timeout=settings.llm_http_timeout
        )
    return ChatOpenAI(**kwargs)


class ChatSessionNotFoundError(Exception):
    """세션이 없거나 현재 테넌트/봇 소유가 아닐 때(존재 비노출 위해 404)."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(f"chat session not found: {session_id}")


class ChatService:
    """chat 메인 파이프라인 + 히스토리 + 모델목록 서비스."""

    def __init__(self, db: Session, vector_store=None, llm=None) -> None:
        self.db = db
        self._vector_store = vector_store  # 없으면 lazy(get_policy_vector_store)
        self._llm = llm  # 주입 시 모든 LLM 작업에 사용(테스트). 없으면 봇별 build_chat_llm.

    @property
    def vector_store(self):
        if self._vector_store is None:
            self._vector_store = get_policy_vector_store()
        return self._vector_store

    def _llm_for(self, bot: Bot):
        """주입 LLM 우선(테스트), 없으면 봇 설정으로 ChatOpenAI 구성."""
        if self._llm is not None:
            return self._llm
        return build_chat_llm(
            model=bot.llm_model,
            temperature=bot.llm_temperature,
            max_tokens=bot.max_answer_length,
        )

    # ------------------------------------------------------------------ #
    # Bot / Session helpers
    # ------------------------------------------------------------------ #
    def _get_active_bot(self, bot_id: str, tenant: TenantContext) -> Bot:
        """테넌트 소유 + 비-DELETING 봇 검증. 없으면 404, 비활성이면 409."""
        stmt = select(Bot).where(
            Bot.id == bot_id,
            Bot.company_id == tenant.company_id,
            Bot.workplace_id == tenant.workplace_id,
            Bot.status != STATUS_DELETING,
        )
        bot = self.db.execute(stmt).scalar_one_or_none()
        if bot is None:
            raise BotNotFoundError(bot_id)
        if bot.disabled:
            raise BotDisabledError(bot_id)
        return bot

    def _get_owned_session(self, session_id: str, tenant: TenantContext) -> ChatSession:
        stmt = select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.company_id == tenant.company_id,
            ChatSession.workplace_id == tenant.workplace_id,
        )
        session = self.db.execute(stmt).scalar_one_or_none()
        if session is None:
            raise ChatSessionNotFoundError(session_id)
        return session

    def _get_or_create_session(
        self, tenant: TenantContext, bot: Bot, session_id: str | None, channel: str | None
    ) -> ChatSession:
        if session_id:
            session = self._get_owned_session(session_id, tenant)
            if session.bot_id != bot.id:  # 다른 봇 세션이면 노출 차단(404)
                raise ChatSessionNotFoundError(session_id)
            return session
        session = ChatSession(
            company_id=tenant.company_id,
            workplace_id=tenant.workplace_id,
            bot_id=bot.id,
            channel=channel or "web",
        )
        self.db.add(session)
        self.db.flush()  # session.id 확보
        return session

    # ------------------------------------------------------------------ #
    # Retrieval (봇 전용 필터 — Rule #1·#5)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _policy_filter(tenant: TenantContext, bot_id: str) -> qmodels.Filter:
        """company_id + workplace_id + domain="policy" + owner_id=bot_id 격리 필터."""
        return qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="metadata.company_id",
                    match=qmodels.MatchValue(value=tenant.company_id),
                ),
                qmodels.FieldCondition(
                    key="metadata.workplace_id",
                    match=qmodels.MatchValue(value=tenant.workplace_id),
                ),
                qmodels.FieldCondition(
                    key="metadata.domain",
                    match=qmodels.MatchValue(value="policy"),
                ),
                qmodels.FieldCondition(
                    key="metadata.owner_id",
                    match=qmodels.MatchValue(value=bot_id),
                ),
            ]
        )

    def _retrieve(self, tenant: TenantContext, bot: Bot, query: str):
        """봇 전용 필터로 top_k 유사 청크 검색. 반환: [(Document, score), ...]."""
        return self.vector_store.similarity_search_with_score(
            query, k=bot.top_k, filter=self._policy_filter(tenant, bot.id)
        )

    # ------------------------------------------------------------------ #
    # History
    # ------------------------------------------------------------------ #
    def _load_history(self, session_id: str, turns: int) -> list[ChatMessage]:
        """최근 `turns` 턴(=2*turns 메시지)을 seq 순으로 로드(현재 질문 추가 이전 호출)."""
        if turns <= 0:
            return []
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.seq.asc(), ChatMessage.created_at.asc())
        )
        rows = list(self.db.execute(stmt).scalars().all())
        return rows[-(turns * 2):]

    @staticmethod
    def _format_history(messages: list[ChatMessage]) -> str:
        lines = []
        for m in messages:
            label = "사용자" if m.role == "user" else "도우미"
            lines.append(f"{label}: {(m.content or '')[:_MAX_MSG_CHARS]}")
        return "\n".join(lines)

    def _session_has_rag_context(self, session_id: str) -> bool:
        """세션의 assistant 메시지 중 sources_json 이 실린 적이 있는가(Rule #3 폴백 판단)."""
        cnt = self.db.execute(
            select(func.count())
            .select_from(ChatMessage)
            .where(
                ChatMessage.session_id == session_id,
                ChatMessage.role == "assistant",
                ChatMessage.sources_json.is_not(None),
            )
        ).scalar_one()
        return cnt > 0

    # ------------------------------------------------------------------ #
    # Generation
    # ------------------------------------------------------------------ #
    @staticmethod
    def _usage(resp) -> tuple[int, int]:
        usage = getattr(resp, "usage_metadata", None) or {}
        return int(usage.get("input_tokens", 0) or 0), int(usage.get("output_tokens", 0) or 0)

    def _generate(self, bot: Bot, history_text: str, query: str, docs_scores) -> tuple[str, int, int]:
        """검색 문맥(+히스토리)으로 답변 생성. bot.system_prompt/temperature/max_answer_length 적용."""
        context = "\n\n".join(doc.page_content for doc, _ in docs_scores)
        system = bot.system_prompt or _DEFAULT_SYSTEM_PROMPT
        human = ""
        if history_text:
            human += f"이전 대화:\n{history_text}\n\n"
        human += (
            f"참고 문맥:\n{context}\n\n질문: {query}\n\n"
            "위 '참고 문맥' 만 근거로 한국어로 간결하게 답변하세요."
        )
        resp = self._llm_for(bot).invoke([("system", system), ("human", human)])
        answer = (getattr(resp, "content", "") or "").strip() or _NO_CONTEXT_ANSWER
        in_tok, out_tok = self._usage(resp)
        return answer, in_tok, out_tok

    def _answer_from_history(self, bot: Bot, history_text: str, query: str) -> tuple[str, int, int]:
        """HISTORY_ONLY — 검색 없이 이전 대화만 가공(요약/번역 등)."""
        resp = self._llm_for(bot).invoke(
            [("system", _HISTORY_ONLY_SYSTEM), ("human", f"이전 대화:\n{history_text}\n\n요청: {query}")]
        )
        answer = (getattr(resp, "content", "") or "").strip() or _NO_CONTEXT_ANSWER
        in_tok, out_tok = self._usage(resp)
        return answer, in_tok, out_tok

    def _build_sources(self, docs_scores) -> list[ChatSource]:
        """검색 결과를 ChatSource 로 포맷. file_name 은 doc_id 일괄 조회로 채운다."""
        doc_ids = [
            (doc.metadata or {}).get("doc_id")
            for doc, _ in docs_scores
            if (doc.metadata or {}).get("doc_id")
        ]
        file_names: dict = {}
        if doc_ids:
            rows = self.db.execute(
                select(Document.id, Document.file_name).where(Document.id.in_(set(doc_ids)))
            ).all()
            file_names = {r.id: r.file_name for r in rows}

        sources: list[ChatSource] = []
        for doc, score in docs_scores:
            md = doc.metadata or {}
            did = md.get("doc_id")
            sources.append(
                ChatSource(
                    doc_id=did or "",
                    title=md.get("title"),
                    file_name=file_names.get(did),
                    snippet=(doc.page_content or "")[:_SNIPPET_MAX],
                    score=float(score) if score is not None else None,
                    chunk_index=md.get("chunk_index"),
                    document_url=f"/api/v1/documents/{did}/download" if did else None,
                )
            )
        return sources

    # ------------------------------------------------------------------ #
    # Chat (8단계 파이프라인 — 설계 §5.2)
    # ------------------------------------------------------------------ #
    def chat(self, tenant: TenantContext, payload: PolicyChatRequest) -> dict:
        """RAG 채팅 메인. 반환: {answer, session_id, sources}."""
        # 1. 봇 검증 — 존재/소유(404), disabled(409)
        bot = self._get_active_bot(payload.bot_id, tenant)

        # 2. 세션 조회/생성
        session = self._get_or_create_session(
            tenant, bot, payload.session_id, payload.channel
        )

        # 3. 히스토리 로드 (현재 질문 저장 이전 — 직전까지의 대화)
        next_seq = self.db.execute(
            select(func.count())
            .select_from(ChatMessage)
            .where(ChatMessage.session_id == session.id)
        ).scalar_one()
        history = self._load_history(session.id, bot.history_turns)
        history_text = self._format_history(history)

        # 사용자 메시지 저장
        self.db.add(
            ChatMessage(
                session_id=session.id, seq=next_seq, role="user", content=payload.query
            )
        )

        # 4. 의도 분류 + Rule #3 강제 폴백
        #    - 첫 턴(히스토리 없음): 무조건 RETRIEVE (검색 없이 답하면 환각).
        #    - 그 외: LLM 분류. 단 HISTORY_ONLY 라도 세션에 RAG 출처 컨텍스트가 전무하면
        #      강제로 RETRIEVE 로 전환한다(이전 답변에 sources 가 한 번도 없었음 = 가공할 근거 없음).
        if not history:
            intent = Intent.RETRIEVE
        else:
            intent = classify_intent(payload.query, history_text, self._llm_for(bot))
            if intent == Intent.HISTORY_ONLY and not self._session_has_rag_context(session.id):
                logger.info(
                    "Rule#3 폴백: HISTORY_ONLY -> RETRIEVE (세션에 RAG 출처 컨텍스트 없음) session=%s",
                    session.id,
                )
                intent = Intent.RETRIEVE

        # 5~8. 검색/생성
        sources: list[ChatSource] = []
        if intent == Intent.HISTORY_ONLY:
            answer, in_tok, out_tok = self._answer_from_history(bot, history_text, payload.query)
        else:
            # 5. 후속질문 검색어 재작성(지시어 있을 때만 LLM 1콜)
            search_query = payload.query
            if history and needs_reformulation(payload.query):
                search_query = reformulate_query(payload.query, history_text, self._llm_for(bot))
            # 6. 벡터 검색 (봇 전용 필터)
            docs_scores = self._retrieve(tenant, bot, search_query)
            if not docs_scores:
                # 문맥 없음 -> 결정론적 '모른다'(LLM 호출 없이 환각 차단)
                answer, in_tok, out_tok = _NO_CONTEXT_ANSWER, 0, 0
            else:
                # 7~8. LLM 생성 + sources 구성
                answer, in_tok, out_tok = self._generate(
                    bot, history_text, payload.query, docs_scores
                )
                sources = self._build_sources(docs_scores)

        # sources 노출 규칙 — source_expose=false 또는 '문맥없음' 답변이면 숨김(설계 §5.2)
        if not bot.source_expose or answer == _NO_CONTEXT_ANSWER:
            sources = []

        # assistant 메시지 저장 (sources 스냅샷 보존 — 폴백 판단/히스토리 재구성)
        self.db.add(
            ChatMessage(
                session_id=session.id,
                seq=next_seq + 1,
                role="assistant",
                content=answer,
                input_tokens=in_tok,
                output_tokens=out_tok,
                sources_json=(
                    json.dumps([s.model_dump() for s in sources], ensure_ascii=False)
                    if sources
                    else None
                ),
            )
        )
        self.db.commit()
        self.db.refresh(session)

        return {"answer": answer, "session_id": session.id, "sources": sources}

    # ------------------------------------------------------------------ #
    # History 조회 (§5.1)
    # ------------------------------------------------------------------ #
    def get_history(self, tenant: TenantContext, session_id: str) -> ChatHistoryResponse:
        """세션 히스토리 조회. 테넌트 소유가 아니면 404."""
        session = self._get_owned_session(session_id, tenant)
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.seq.asc(), ChatMessage.created_at.asc())
        )
        rows = self.db.execute(stmt).scalars().all()

        messages = [
            ChatMessageResponse(
                id=m.id,
                role=m.role,
                content=m.content,
                input_tokens=m.input_tokens,
                output_tokens=m.output_tokens,
                sources=self._parse_sources(m.sources_json),
                created_at=m.created_at,
            )
            for m in rows
        ]
        return ChatHistoryResponse(
            session_id=session.id,
            bot_id=session.bot_id,
            channel=session.channel,
            messages=messages,
        )

    @staticmethod
    def _parse_sources(sources_json: str | None) -> list[ChatSource]:
        if not sources_json:
            return []
        try:
            raw = json.loads(sources_json)
            return [ChatSource(**item) for item in raw]
        except (ValueError, TypeError):  # 손상된 스냅샷은 무시(히스토리 표시 우선)
            logger.warning("sources_json 파싱 실패 — 빈 목록으로 대체")
            return []

    # ------------------------------------------------------------------ #
    # Models (§5.4)
    # ------------------------------------------------------------------ #
    def get_available_models(self) -> list[str]:
        """사용 가능 LLM 모델 목록. 현 환경은 단일 Qwen 중심 → settings.LLM_MODEL.

        TODO(Phase D): 설정상 대체 모델 목록을 합쳐 반환.
        """
        return [settings.LLM_MODEL]
