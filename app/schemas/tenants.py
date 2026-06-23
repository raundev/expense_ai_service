"""테넌트 화이트리스트 Request/Response DTO (Pydantic v2).

도메인 API 와 달리 company_id/workplace_id 를 '관리자가 명시'해서 등록하므로 Body 로 받는다
(헤더 TenantContext 가 아님). 등록은 관리자 운영 작업이다(app/api/endpoints/tenants.py).
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TenantCreateRequest(BaseModel):
    """테넌트 등록 요청."""

    company_id: str = Field(..., min_length=1, max_length=64, description="회사 식별자")
    workplace_id: str = Field(..., min_length=1, max_length=64, description="사업장 식별자")
    company_name: str | None = Field(None, max_length=255, description="회사명(선택, 표시용)")
    workplace_name: str | None = Field(None, max_length=255, description="사업장명(선택, 표시용)")


class TenantUpdateRequest(BaseModel):
    """테넌트 상태/표시명 수정 (PATCH — 전달된 필드만 갱신).

    status 를 "SUSPENDED" 로 두면 등록돼 있어도 도메인 접근이 차단되고, "ACTIVE" 로
    되돌리면 복구된다.
    """

    status: Literal["ACTIVE", "SUSPENDED"] | None = Field(
        None, description='"ACTIVE"(허용) 또는 "SUSPENDED"(차단)'
    )
    company_name: str | None = Field(None, max_length=255)
    workplace_name: str | None = Field(None, max_length=255)


class TenantResponse(BaseModel):
    """테넌트 단건/목록 응답."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    workplace_id: str
    company_name: str | None
    workplace_name: str | None
    status: str
    created_at: datetime
    updated_at: datetime
