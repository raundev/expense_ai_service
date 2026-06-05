"""Policy RAG 챗봇 — 대화 세션/메시지 모델 (설계 §2.3, §2.4).

ChatSession 은 `(company_id, workplace_id, bot_id)` 로 격리되며 Bot 에 종속된다.
ChatMessage 는 세션의 각 turn(user/assistant)을 적재하고, assistant 메시지에는
`sources_json`(출처 스냅샷)을 남긴다. 이 스냅샷은 ① 히스토리 재구성, ② 의도분류
폴백(Critical Design Rule #3 — 세션에 RAG 출처 컨텍스트가 있었는지 판단)에 쓰인다.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ChatSession(Base):
    """봇과의 대화 세션. session_id 단위로 히스토리를 묶는다."""

    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    # --- 테넌트 식별 (조회/격리 키) ---
    company_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    workplace_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    bot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("bots.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    channel: Mapped[str] = mapped_column(
        String(16), nullable=False, default="web", server_default=text("'web'")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    bot: Mapped["Bot"] = relationship(back_populates="sessions")
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ChatSession id={self.id!r} bot_id={self.bot_id!r} channel={self.channel!r}>"
        )


class ChatMessage(Base):
    """세션 내 단일 메시지(turn). assistant 메시지는 sources_json 에 출처 스냅샷을 보존."""

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # 세션 내 turn 순서(0-based, 서비스가 부여). created_at 동률(Windows 저해상도 클럭/
    # 초고속 insert) 시에도 user→assistant 순서를 결정론적으로 보장하는 정렬 키.
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # assistant 메시지의 sources 스냅샷(JSON 직렬화 문자열). 히스토리 재구성·폴백 판단용.
    sources_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    session: Mapped["ChatSession"] = relationship(back_populates="messages")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ChatMessage id={self.id!r} session_id={self.session_id!r} role={self.role!r}>"
        )
