"""Policy RAG 챗봇 — Bot 및 추천질문 모델 (설계 §2.1, §2.5).

멀티테넌시(Critical Design Rule #5): 모든 Bot 은 `(company_id, workplace_id)` 를 직접
보유하고, 모든 조회는 이 키로 격리한다. PK 는 외부 노출(URL)·참고문서 정합성을 위해
String(36) UUID(uuid4, 앱 생성)로 통일한다(설계 §2 / D4).

삭제(Critical Design Rule #4 — Hard Delete 금지): Bot 은 즉시 물리 삭제하지 않는다.
`status="DELETING"` 으로 전이(조회/chat 에서 즉시 제외)한 뒤, 백그라운드 정리 함수가
소속 문서(domain="policy", owner_id=bot_id)의 벡터·파일을 정리하고 **마지막에** 행을
제거한다(§4.3). 그 최종 물리 삭제 시 세션·메시지·추천질문이 함께 제거되도록 relationship
에 `cascade="all, delete-orphan"` 을 건다. SQLite 는 FK 를 강제하지 않으므로 파이썬
레벨 cascade 가 정합성을 보장한다(§2.5).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


def _uuid() -> str:
    """앱 레벨 UUID(uuid4) 생성기. SQLite/PostgreSQL 양쪽 호환 String(36) PK."""
    return str(uuid.uuid4())


class Bot(Base):
    """테넌트가 보유하는 챗봇. 봇별 LLM 설정을 오버라이드한다."""

    __tablename__ = "bots"
    __table_args__ = (
        # 테넌트 내 봇 이름 중복 방지.
        UniqueConstraint("company_id", "workplace_id", "name", name="uq_bot_tenant_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    # --- 테넌트 식별 (조회/격리 키) ---
    company_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    workplace_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # --- LLM 설정 오버라이드 (검증 범위는 스키마에서 강제: 설계 §2.1) ---
    llm_model: Mapped[str] = mapped_column(String(128), nullable=False)
    llm_temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_answer_length: Mapped[int] = mapped_column(Integer, nullable=False, default=2048)
    history_turns: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_expose: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    # --- 생성 직후 비활성(설계 §2.1). server_default 는 PG/SQLite 양쪽 호환 text("true"). ---
    disabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    # --- Soft Delete 상태(설계 §4.3): "ACTIVE" | "DELETING". DELETING 은 조회/chat 즉시 제외. ---
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ACTIVE", server_default=text("'ACTIVE'")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # --- 관계 (최종 물리 삭제 시 파이썬 레벨 cascade) ---
    recommended_questions: Mapped[list["BotRecommendedQuestion"]] = relationship(
        back_populates="bot",
        cascade="all, delete-orphan",
        order_by="BotRecommendedQuestion.sort_order",
    )
    sessions: Mapped[list["ChatSession"]] = relationship(
        back_populates="bot",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Bot id={self.id!r} name={self.name!r} "
            f"status={self.status!r} disabled={self.disabled}>"
        )


class BotRecommendedQuestion(Base):
    """봇의 UI 초기화면 추천 질문. create/update 에서 동기화, recommend 는 조회 전용(§6.3)."""

    __tablename__ = "bot_recommended_questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    bot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("bots.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    question: Mapped[str] = mapped_column(String(512), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    bot: Mapped["Bot"] = relationship(back_populates="recommended_questions")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<BotRecommendedQuestion id={self.id!r} bot_id={self.bot_id!r} "
            f"order={self.sort_order}>"
        )
