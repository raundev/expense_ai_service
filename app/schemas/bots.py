"""Policy RAG 챗봇 — Bot Request/Response DTO (Pydantic v2, 설계 §2.1·§6).

company_id / workplace_id 는 헤더(TenantContext)에서 강제 주입되므로 Body 에서 받지 않는다.
검증 범위는 설계 §2.1 제약을 계승한다(temperature 0~1, max_answer_length 64~8192,
history_turns 0~20, top_k 1~50).
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# 검증 범위 상수 (설계 §2.1) — 모델 컬럼 기본값과 일치.
_TEMP_GE, _TEMP_LE = 0.0, 1.0
_MAXLEN_GE, _MAXLEN_LE = 64, 8192
_HIST_GE, _HIST_LE = 0, 20
_TOPK_GE, _TOPK_LE = 1, 50


class BotCreateRequest(BaseModel):
    """봇 생성 요청. 생성 직후 봇은 비활성(disabled=true) 상태다(설계 §2.1)."""

    name: str = Field(..., min_length=1, max_length=255, description="봇 이름(테넌트 내 유일)")
    llm_model: str | None = Field(
        None,
        max_length=128,
        description="봇이 사용할 LLM 모델. 미지정 시 서버 기본(settings.LLM_MODEL)을 서비스가 적용.",
    )
    llm_temperature: float = Field(0.0, ge=_TEMP_GE, le=_TEMP_LE)
    max_answer_length: int = Field(2048, ge=_MAXLEN_GE, le=_MAXLEN_LE)
    history_turns: int = Field(5, ge=_HIST_GE, le=_HIST_LE)
    top_k: int = Field(5, ge=_TOPK_GE, le=_TOPK_LE)
    system_prompt: str | None = Field(None, description="봇 시스템 프롬프트(없으면 기본 사용)")
    source_expose: bool = Field(True, description="답변에 출처(sources) 노출 여부")
    recommended_questions: list[str] = Field(
        default_factory=list, description="UI 초기화면 추천 질문(입력 순서대로 sort_order 부여)"
    )


class BotUpdateRequest(BaseModel):
    """봇 설정 수정 (PATCH 시맨틱 — 전달된 필드만 갱신).

    서비스는 `model_dump(exclude_unset=True)` 로 '미전달' 과 'null 로 명시 초기화' 를 구분한다.
    recommended_questions 는 제공(None 이 아님) 시 전체 교체, 미전달 시 유지.
    """

    name: str | None = Field(None, min_length=1, max_length=255)
    llm_model: str | None = Field(None, max_length=128)
    llm_temperature: float | None = Field(None, ge=_TEMP_GE, le=_TEMP_LE)
    max_answer_length: int | None = Field(None, ge=_MAXLEN_GE, le=_MAXLEN_LE)
    history_turns: int | None = Field(None, ge=_HIST_GE, le=_HIST_LE)
    top_k: int | None = Field(None, ge=_TOPK_GE, le=_TOPK_LE)
    system_prompt: str | None = None
    source_expose: bool | None = None
    recommended_questions: list[str] | None = None


class RecommendedQuestionResponse(BaseModel):
    """추천 질문 1건 (GET /bots/{bot_id}/recommend, 설계 §6.3)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    question: str
    sort_order: int


class BotResponse(BaseModel):
    """봇 단건/목록 응답."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    workplace_id: str
    name: str
    llm_model: str
    llm_temperature: float
    max_answer_length: int
    history_turns: int
    top_k: int
    system_prompt: str | None
    source_expose: bool
    disabled: bool
    status: str
    created_at: datetime
    updated_at: datetime
    # ORM relationship(sort_order 정렬)에서 그대로 매핑.
    recommended_questions: list[RecommendedQuestionResponse] = Field(default_factory=list)


class BotStatisticsResponse(BaseModel):
    """GET /bots/{bot_id}/statistics 응답 (설계 §6.2)."""

    bot_id: str
    document_count: int = 0
    session_count: int = 0
    message_count: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0


class DailyStatPoint(BaseModel):
    """일별 통계 한 점 (날짜·건수)."""

    date: str
    count: int


class BotDailyStatisticsResponse(BaseModel):
    """GET /bots/{bot_id}/statistics/daily 응답 (설계 §6.2)."""

    bot_id: str
    window_days: int
    sessions_daily: list[DailyStatPoint] = Field(default_factory=list)
