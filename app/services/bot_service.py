"""Policy RAG 챗봇 — Bot 도메인 서비스 (설계 §6).

모든 조회·변경은 TenantContext(company_id + workplace_id)로 격리한다(Critical Design
Rule #5). 봇 삭제는 Hard Delete 하지 않고 `status="DELETING"` 으로 전이만 한다(Rule #4);
실제 벡터/파일/행 물리 정리는 백그라운드 워커(별도 페이즈)가 멱등 수행한다.

DB 전용 도메인 로직(LLM 미사용). 통계는 dialect 비종속을 위해 단순 count/sum 과
파이썬 날짜 버킷팅을 사용한다(SQLite/PostgreSQL 양쪽 호환, 설계 §6.2).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import TenantContext
from app.models.bots import Bot, BotRecommendedQuestion
from app.models.chat import ChatMessage, ChatSession
from app.models.documents import Document
from app.schemas.bots import BotCreateRequest, BotUpdateRequest

logger = logging.getLogger(__name__)

# Soft Delete 상태값(설계 §4.3). 조회/통계에서 즉시 제외한다.
STATUS_ACTIVE = "ACTIVE"
STATUS_DELETING = "DELETING"


class BotNotFoundError(Exception):
    """봇이 없거나 현재 테넌트 소유가 아니거나 DELETING 상태일 때(존재 비노출 위해 404)."""

    def __init__(self, bot_id: str) -> None:
        self.bot_id = bot_id
        super().__init__(f"bot not found: {bot_id}")


class BotNameConflictError(Exception):
    """테넌트 내 동일 이름 봇이 이미 존재할 때(유니크 제약, 409)."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"bot name already exists in tenant: {name}")


class BotDisabledError(Exception):
    """비활성(disabled) 봇으로 chat 을 시도할 때(409). chat_service 가 사용한다."""

    def __init__(self, bot_id: str) -> None:
        self.bot_id = bot_id
        super().__init__(f"bot is disabled: {bot_id}")


class BotService:
    """Bot CRUD / 활성화 / Soft Delete / 통계 / 추천질문 도메인 서비스."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _get_owned(self, bot_id: str, tenant: TenantContext) -> Bot:
        """현재 테넌트 소유 + 비-DELETING 봇 조회. 없으면 BotNotFoundError(404)."""
        stmt = select(Bot).where(
            Bot.id == bot_id,
            Bot.company_id == tenant.company_id,
            Bot.workplace_id == tenant.workplace_id,
            Bot.status != STATUS_DELETING,
        )
        bot = self.db.execute(stmt).scalar_one_or_none()
        if bot is None:
            raise BotNotFoundError(bot_id)
        return bot

    @staticmethod
    def _sync_recommended_questions(bot: Bot, questions: list[str]) -> None:
        """추천 질문 전체 교체. cascade=all,delete-orphan 이 기존 행을 정리한다."""
        bot.recommended_questions = [
            BotRecommendedQuestion(question=q, sort_order=i)
            for i, q in enumerate(questions)
        ]

    # ------------------------------------------------------------------ #
    # CRUD
    # ------------------------------------------------------------------ #
    def create_bot(self, payload: BotCreateRequest, tenant: TenantContext) -> Bot:
        """봇 생성. 생성 직후 비활성(disabled=True). 이름 중복 시 BotNameConflictError(409).

        llm_model 미지정 시 서버 기본(settings.LLM_MODEL)을 적용한다.
        """
        # DB 유니크 제약(company, workplace, name) 위반을 피하기 위한 선검사(상태 무관).
        exists = self.db.execute(
            select(Bot.id).where(
                Bot.company_id == tenant.company_id,
                Bot.workplace_id == tenant.workplace_id,
                Bot.name == payload.name,
            )
        ).first()
        if exists is not None:
            raise BotNameConflictError(payload.name)

        bot = Bot(
            company_id=tenant.company_id,
            workplace_id=tenant.workplace_id,
            name=payload.name,
            llm_model=payload.llm_model or settings.LLM_MODEL,
            llm_temperature=payload.llm_temperature,
            max_answer_length=payload.max_answer_length,
            history_turns=payload.history_turns,
            top_k=payload.top_k,
            system_prompt=payload.system_prompt,
            source_expose=payload.source_expose,
            disabled=True,  # 설계 §2.1 — 생성 직후 비활성
            status=STATUS_ACTIVE,
        )
        self._sync_recommended_questions(bot, payload.recommended_questions)
        self.db.add(bot)
        self.db.commit()
        self.db.refresh(bot)
        logger.info(
            "봇 생성: tenant=%s/%s id=%s name=%r",
            tenant.company_id, tenant.workplace_id, bot.id, bot.name,
        )
        return bot

    def get_bot(self, bot_id: str, tenant: TenantContext) -> Bot:
        return self._get_owned(bot_id, tenant)

    def list_bots(self, tenant: TenantContext) -> list[Bot]:
        """테넌트 봇 목록(name ASC, DELETING 제외)."""
        stmt = (
            select(Bot)
            .where(
                Bot.company_id == tenant.company_id,
                Bot.workplace_id == tenant.workplace_id,
                Bot.status != STATUS_DELETING,
            )
            .order_by(Bot.name.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def update_bot(
        self, bot_id: str, payload: BotUpdateRequest, tenant: TenantContext
    ) -> Bot:
        """PATCH 시맨틱 수정. exclude_unset 으로 '미전달' 과 'null 명시'를 구분한다."""
        bot = self._get_owned(bot_id, tenant)
        data = payload.model_dump(exclude_unset=True)
        questions = data.pop("recommended_questions", None)

        # 이름 변경 시 테넌트 내 중복 선검사.
        new_name = data.get("name")
        if new_name is not None and new_name != bot.name:
            dup = self.db.execute(
                select(Bot.id).where(
                    Bot.company_id == tenant.company_id,
                    Bot.workplace_id == tenant.workplace_id,
                    Bot.name == new_name,
                    Bot.id != bot.id,
                )
            ).first()
            if dup is not None:
                raise BotNameConflictError(new_name)

        for key, value in data.items():
            setattr(bot, key, value)
        if questions is not None:  # 제공되면 전체 교체, 미전달이면 유지
            self._sync_recommended_questions(bot, questions)

        self.db.commit()
        self.db.refresh(bot)
        return bot

    def set_disabled(self, bot_id: str, tenant: TenantContext, *, disabled: bool) -> Bot:
        """활성화/비활성화 공통 (enable=disabled False, disable=disabled True)."""
        bot = self._get_owned(bot_id, tenant)
        bot.disabled = disabled
        self.db.commit()
        self.db.refresh(bot)
        return bot

    def soft_delete_bot(self, bot_id: str, tenant: TenantContext) -> Bot:
        """Soft Delete — status="DELETING" 으로 전이만 한다(Rule #4). 즉시 조회/chat 제외.

        실제 물리 정리(소속 documents 의 벡터/파일 정리 → 봇·세션·메시지·추천질문 행 제거)는
        백그라운드 워커가 멱등 수행한다(설계 §4.3 step 3, 별도 페이즈).
        """
        bot = self._get_owned(bot_id, tenant)
        bot.status = STATUS_DELETING

        # Cascade Soft Delete: 봇 소유 문서(owner_id=bot_id)도 즉시 DELETING 으로 전이한다
        # (검색/목록에서 즉시 제외 — 설계 §4.3 step3). 물리 정리는 cleanup 워커가 수행.
        owned_docs = self.db.execute(
            select(Document).where(
                Document.company_id == tenant.company_id,
                Document.workplace_id == tenant.workplace_id,
                Document.owner_id == bot_id,
                Document.embedding_status != STATUS_DELETING,
            )
        ).scalars().all()
        for doc in owned_docs:
            doc.embedding_status = STATUS_DELETING

        self.db.commit()
        self.db.refresh(bot)
        logger.info(
            "봇 Soft Delete(status=DELETING): tenant=%s/%s id=%s + 소속문서 %d건 DELETING 전이",
            tenant.company_id, tenant.workplace_id, bot.id, len(owned_docs),
        )
        # 물리 정리(벡터→파일→행 + 봇 행)는 cleanup_service.run_cleanup 가 멱등 수행한다.
        return bot

    # ------------------------------------------------------------------ #
    # Recommend (§6.3)
    # ------------------------------------------------------------------ #
    def get_recommended_questions(
        self, bot_id: str, tenant: TenantContext
    ) -> list[BotRecommendedQuestion]:
        bot = self._get_owned(bot_id, tenant)
        return list(bot.recommended_questions)  # relationship 가 sort_order ASC 정렬

    # ------------------------------------------------------------------ #
    # Sessions (§6.1)
    # ------------------------------------------------------------------ #
    def list_sessions(self, bot_id: str, tenant: TenantContext) -> list[ChatSession]:
        self._get_owned(bot_id, tenant)  # 소유/존재 검증(404)
        stmt = (
            select(ChatSession)
            .where(
                ChatSession.company_id == tenant.company_id,
                ChatSession.workplace_id == tenant.workplace_id,
                ChatSession.bot_id == bot_id,
            )
            .order_by(ChatSession.updated_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    # ------------------------------------------------------------------ #
    # Statistics (§6.2)
    # ------------------------------------------------------------------ #
    def get_statistics(self, bot_id: str, tenant: TenantContext) -> dict:
        """문서/세션/메시지/토큰 합계 — 전부 bot+테넌트 필터."""
        self._get_owned(bot_id, tenant)

        document_count = self.db.execute(
            select(func.count())
            .select_from(Document)
            .where(
                Document.company_id == tenant.company_id,
                Document.workplace_id == tenant.workplace_id,
                Document.domain == "policy",
                Document.owner_id == bot_id,
                Document.embedding_status != STATUS_DELETING,
            )
        ).scalar_one()

        session_count = self.db.execute(
            select(func.count())
            .select_from(ChatSession)
            .where(
                ChatSession.company_id == tenant.company_id,
                ChatSession.workplace_id == tenant.workplace_id,
                ChatSession.bot_id == bot_id,
            )
        ).scalar_one()

        msg_row = self.db.execute(
            select(
                func.count().label("cnt"),
                func.coalesce(func.sum(ChatMessage.input_tokens), 0).label("in_tok"),
                func.coalesce(func.sum(ChatMessage.output_tokens), 0).label("out_tok"),
            )
            .select_from(ChatMessage)
            .join(ChatSession, ChatMessage.session_id == ChatSession.id)
            .where(
                ChatSession.company_id == tenant.company_id,
                ChatSession.workplace_id == tenant.workplace_id,
                ChatSession.bot_id == bot_id,
            )
        ).one()

        return {
            "bot_id": bot_id,
            "document_count": int(document_count),
            "session_count": int(session_count),
            "message_count": int(msg_row.cnt),
            "total_input_tokens": int(msg_row.in_tok),
            "total_output_tokens": int(msg_row.out_tok),
        }

    def get_daily_statistics(
        self, bot_id: str, tenant: TenantContext, window_days: int = 7
    ) -> dict:
        """최근 N일 세션 수. DB date 함수 차이를 피해 파이썬에서 날짜 버킷팅(§6.2)."""
        self._get_owned(bot_id, tenant)

        today = datetime.utcnow().date()
        start_day = today - timedelta(days=window_days - 1)
        cutoff_dt = datetime.combine(start_day, datetime.min.time())

        created_ats = self.db.execute(
            select(ChatSession.created_at).where(
                ChatSession.company_id == tenant.company_id,
                ChatSession.workplace_id == tenant.workplace_id,
                ChatSession.bot_id == bot_id,
                ChatSession.created_at >= cutoff_dt,
            )
        ).scalars().all()

        bucket: dict = {}
        for dt in created_ats:
            day = dt.date()
            bucket[day] = bucket.get(day, 0) + 1

        points = [
            {
                "date": str(start_day + timedelta(days=i)),
                "count": bucket.get(start_day + timedelta(days=i), 0),
            }
            for i in range(window_days)
        ]
        return {"bot_id": bot_id, "window_days": window_days, "sessions_daily": points}
