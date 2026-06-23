"""테넌트 화이트리스트 — 관리자 등록/조회/수정 API — [tag: Admin API].

미등록 (company_id, workplace_id) 의 도메인 데이터 생성/접근을 차단하기 위한 화이트리스트
관리 엔드포인트. 도메인 라우터와 달리 테넌트 헤더를 요구하지 않으며, `require_registered_tenant`
게이트의 적용도 받지 않는다(닭-달걀 방지: 테넌트 등록 자체가 막히면 안 됨).

⚠️ 운영 보안: 이 등록 API 자체는 내부망/관리자 인증으로 보호해야 한다(admin.py 와 동일 주의).
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import ApiResponse
from app.schemas.tenants import TenantCreateRequest, TenantResponse, TenantUpdateRequest
from app.services.tenant_service import (
    TenantAlreadyExistsError,
    TenantNotFoundError,
    TenantService,
)

router = APIRouter()


def get_tenant_service(db: Annotated[Session, Depends(get_db)]) -> TenantService:
    """TenantService 주입용 의존성(테스트에서 dependency_overrides 로 교체 가능)."""
    return TenantService(db)


@router.post(
    "",
    response_model=ApiResponse[TenantResponse],
    status_code=status.HTTP_201_CREATED,
    summary="테넌트 등록 (회사/사업장 화이트리스트 추가)",
)
def register_tenant(
    payload: TenantCreateRequest,
    service: Annotated[TenantService, Depends(get_tenant_service)],
) -> ApiResponse[TenantResponse]:
    try:
        tenant = service.register(payload)
    except TenantAlreadyExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ApiResponse.ok(TenantResponse.model_validate(tenant))


@router.get(
    "",
    response_model=ApiResponse[list[TenantResponse]],
    summary="테넌트 목록 조회",
)
def list_tenants(
    service: Annotated[TenantService, Depends(get_tenant_service)],
) -> ApiResponse[list[TenantResponse]]:
    tenants = service.list_tenants()
    return ApiResponse.ok([TenantResponse.model_validate(t) for t in tenants])


@router.patch(
    "/{tenant_id}",
    response_model=ApiResponse[TenantResponse],
    summary="테넌트 상태/표시명 수정 (SUSPENDED 로 차단 또는 ACTIVE 로 복구)",
)
def update_tenant(
    tenant_id: str,
    payload: TenantUpdateRequest,
    service: Annotated[TenantService, Depends(get_tenant_service)],
) -> ApiResponse[TenantResponse]:
    try:
        tenant = service.update(tenant_id, payload)
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ApiResponse.ok(TenantResponse.model_validate(tenant))
