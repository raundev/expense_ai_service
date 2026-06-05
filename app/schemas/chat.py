"""Policy RAG 챗봇 — 출처/세션/메시지 및 모델목록 DTO (Pydantic v2, 설계 §5).

ChatSource 는 chat 응답과 히스토리 양쪽에서 쓰이는 공통 출처 스키마라 여기에 둔다
(policies.py 가 이를 import). 순환참조를 피하기 위해 chat.py 는 policies.py 를 import 하지 않는다.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChatSource(BaseModel):
    """RAG 답변 근거 출처 1건 (설계 §5.1).

    `bot.source_expose=false` 이거나 답변이 _NO_CONTEXT_ANSWER 류이면 서비스가 sources 를
    비워 반환한다(노출 규칙은 chat_service 책임).
    """

    doc_id: str = Field(..., description="출처 문서 UUID(Document.id)")
    title: str | None = Field(None, description="문서 제목")
    file_name: str | None = Field(None, description="원본 파일명(텍스트 적재 시 null)")
    snippet: str = Field("", max_length=300, description="본문 일부(≤300자)")
    score: float | None = Field(None, description="유사도 점수")
    chunk_index: int | None = Field(None, description="청크 인덱스")
    document_url: str | None = Field(
        None, description="원본 다운로드 URL: /api/v1/documents/{doc_id}/download"
    )


class ChatMessageResponse(BaseModel):
    """히스토리 메시지 1건. sources 는 sources_json 을 파싱해 서비스가 채운다(수동 구성)."""

    id: str
    role: str = Field(..., description='"user" | "assistant"')
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    sources: list[ChatSource] = Field(default_factory=list)
    created_at: datetime


class ChatHistoryResponse(BaseModel):
    """GET /policies/chat/history/{session_id} 응답 (설계 §5.1)."""

    session_id: str
    bot_id: str
    channel: str
    messages: list[ChatMessageResponse] = Field(default_factory=list)


class BotSessionSummary(BaseModel):
    """GET /bots/{bot_id}/sessions 목록 아이템 (설계 §6.1)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    bot_id: str
    channel: str
    created_at: datetime
    updated_at: datetime


class ChatModelsResponse(BaseModel):
    """GET /policies/chat/models 응답 (설계 §5.4)."""

    models: list[str] = Field(default_factory=list)
