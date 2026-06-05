"""Policy RAG — ingest/chat DTO (Pydantic v2).

chat 계약은 설계 §5.1 로 변경된다: 요청에 `bot_id`(필수)·`session_id`·`channel`,
응답에 `session_id`·`sources` 가 추가된다. (기존 `/policies/chat` 대비 Breaking — §9.3)

ingest 스키마는 공통 `/documents/ingest-text` 로 이관 예정이며, 한시적 alias 용도로 유지한다.
출처(ChatSource)는 chat 응답과 히스토리 공통이라 `schemas/chat.py` 에 정의하고 여기서 import 한다.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.chat import ChatSource


# ---------------------------------------------------------------------------- #
# Ingest (규정 적재) — 전환기 alias (설계 §9.3). 신규 적재는 /documents/ingest-text 사용.
# ---------------------------------------------------------------------------- #
class PolicyIngestRequest(BaseModel):
    """사내 규정 텍스트 적재 요청.

    company_id / workplace_id 는 요청 헤더(TenantContext)에서 강제 주입되므로
    Body 에서 받지 않는다. (다른 도메인과 동일한 멀티테넌트 정책)
    """

    text: str = Field(..., min_length=1, description="적재할 규정 원문 텍스트")
    source_name: str = Field(
        ...,
        max_length=255,
        description="출처 문서명 (예: '취업규칙', '복리후생_2026.pdf')",
    )


class PolicyIngestResponse(BaseModel):
    """규정 적재 결과 요약."""

    source_name: str = Field(..., description="적재한 출처 문서명")
    chunk_count: int = Field(..., description="텍스트가 분할되어 저장된 청크 수")


# ---------------------------------------------------------------------------- #
# Chat (규정 RAG 질의응답) — 설계 §5.1 계약
# ---------------------------------------------------------------------------- #
class PolicyChatRequest(BaseModel):
    """사내 규정 RAG 질의 요청.

    `bot_id` 가 필수로 추가된다(설계 §5.1). 봇별 LLM/검색 설정과 문서 격리
    (domain="policy", owner_id=bot_id)의 기준이 된다.
    """

    bot_id: str = Field(..., description="질의 대상 봇 UUID")
    query: str = Field(..., min_length=1, description="사용자 질문")
    session_id: str | None = Field(
        None, description="대화 세션 UUID. 없으면 신규 세션을 생성한다."
    )
    channel: str | None = Field(
        None, max_length=16, description="대화 채널(기본 'web')."
    )


class PolicyChatResponse(BaseModel):
    """RAG 답변 + 세션/출처."""

    answer: str = Field(..., description="검색된 사내 규정 문맥에 근거한 LLM 답변")
    session_id: str = Field(..., description="대화 세션 UUID(신규 생성 또는 기존)")
    sources: list[ChatSource] = Field(
        default_factory=list,
        description="답변 근거 출처. source_expose=false 이거나 문맥 없음 답변이면 빈 목록.",
    )
