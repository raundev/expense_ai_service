"""공통 Document API — Request/Response DTO (Pydantic v2, 설계 §4).

Critical Design Rule #2(범용성): 본 스키마는 도메인 비종속이다. 소유 주체는 범용 `owner_id`
로만 표현하고 `bot_id` 등 도메인 종속어를 노출하지 않는다. policy 흐름에서는
domain="policy", owner_id=<bot_id> 로 호출한다(타 모듈 재사용 시 의미 혼란 방지).

업로드(multipart) 요청은 Pydantic Body 가 아니라 FastAPI Form/File 파라미터로 받으므로
별도 요청 스키마를 두지 않는다(라우터에서 Form(...)/File(...) 로 처리). 텍스트 적재만
JSON Body(DocumentIngestTextRequest)로 받는다.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DocumentIngestTextRequest(BaseModel):
    """POST /documents/ingest-text — 텍스트 즉시 적재(동기) 요청 (설계 §4.1)."""

    text: str = Field(..., min_length=1, description="적재할 원문 텍스트")
    source_name: str = Field(..., max_length=255, description="출처 표기(검색 source)")
    owner_id: str | None = Field(
        None,
        max_length=36,
        description="문서 소유 주체(범용). policy 도메인에서는 봇 UUID, expense_rule 은 미지정 가능.",
    )
    domain: str = Field(
        "policy", max_length=32, description='문서 도메인(예: "policy", "expense_rule")'
    )
    is_compliance_source: bool = Field(
        False,
        description="영수증 컴플라이언스 RAG 근거 문서 여부. domain=\"expense_rule\" 와 함께 사용(§8).",
    )


class DocumentResponse(BaseModel):
    """문서 메타/상태 응답.

    보안상 서버 내부 경로(file_path)는 응답에 노출하지 않는다(다운로드는 전용 엔드포인트).
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="문서 UUID(= URL 의 doc_id)")
    company_id: str
    workplace_id: str
    domain: str
    owner_id: str | None
    is_compliance_source: bool
    title: str
    file_name: str | None
    content_type: str | None
    byte_size: int | None
    source_name: str
    # "PROCESSING" | "COMPLETED" | "FAILED" | "DELETING"
    embedding_status: str
    error_message: str | None
    chunk_count: int
    created_at: datetime
    updated_at: datetime
