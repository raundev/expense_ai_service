from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------- #
# Ingest (규정 적재)
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
# Chat (규정 질의응답)
# ---------------------------------------------------------------------------- #
class PolicyChatRequest(BaseModel):
    """사내 규정 RAG 질의 요청."""

    query: str = Field(..., min_length=1, description="사용자 질문")


class PolicyChatResponse(BaseModel):
    """RAG 답변."""

    answer: str = Field(..., description="검색된 사내 규정 문맥에 근거한 LLM 답변")
