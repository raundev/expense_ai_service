from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import TenantContext, get_tenant_info
from app.db.session import get_db
from app.schemas.compliance import (
    DashboardKpiResponse,
    ExplanationProcessPayload,
    ExplanationRequestPayload,
)
from app.schemas.transactions import TransactionResultResponse
from app.services.compliance_service import (
    ComplianceService,
    ComplianceTransactionNotFoundError,
)

router = APIRouter()


def get_compliance_service(
    db: Annotated[Session, Depends(get_db)],
) -> ComplianceService:
    """ComplianceService 주입용 의존성 (테스트에서 dependency_overrides 로 교체 가능)."""
    return ComplianceService(db)


def get_admin_id(
    x_admin_id: Annotated[
        str,
        Header(alias="X-Admin-ID", description="요청을 수행하는 관리자 식별자(감사 추적용)"),
    ],
) -> str:
    """소명 요청/처리 시 감사 추적을 위한 관리자 식별자 헤더."""
    return x_admin_id


# ---------------------------------------------------------------------------- #
# GET /dashboard/kpi  — 대시보드 KPI
# ---------------------------------------------------------------------------- #
@router.get(
    "/dashboard/kpi",
    response_model=DashboardKpiResponse,
    summary="컴플라이언스 대시보드 KPI 집계",
)
def get_dashboard_kpi(
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    service: Annotated[ComplianceService, Depends(get_compliance_service)],
    start_date: Annotated[date | None, Query(description="영수증 일자 시작(YYYY-MM-DD)")] = None,
    end_date: Annotated[date | None, Query(description="영수증 일자 종료(YYYY-MM-DD)")] = None,
    department: Annotated[str | None, Query(description="부서(예약: 현재 미적용)")] = None,
) -> DashboardKpiResponse:
    """현재 테넌트 범위의 위반 탐지/소명 상태별 KPI 집계를 반환한다."""
    kpi = service.get_dashboard_kpi(tenant, start_date, end_date, department)
    return DashboardKpiResponse(**kpi)


# ---------------------------------------------------------------------------- #
# GET /transactions  — 위반 영수증 그리드
# ---------------------------------------------------------------------------- #
@router.get(
    "/transactions",
    response_model=list[TransactionResultResponse],
    summary="위반 영수증 목록 조회 (그리드)",
)
def list_violation_transactions(
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    service: Annotated[ComplianceService, Depends(get_compliance_service)],
    status_filter: Annotated[
        str | None,
        Query(alias="status", description="소명 상태 필터(미요청/요청완료/정상처리/위반확정)"),
    ] = None,
    start_date: Annotated[date | None, Query(description="영수증 일자 시작(YYYY-MM-DD)")] = None,
    end_date: Annotated[date | None, Query(description="영수증 일자 종료(YYYY-MM-DD)")] = None,
    department: Annotated[str | None, Query(description="부서(예약: 현재 미적용)")] = None,
    skip: Annotated[int, Query(ge=0, description="페이지네이션 offset")] = 0,
    limit: Annotated[int, Query(ge=1, le=200, description="페이지 크기")] = 50,
) -> list[TransactionResultResponse]:
    """위반(is_compliant=False)으로 탐지된 영수증을 조건/페이지 단위로 조회한다."""
    rows = service.get_violation_list(
        tenant=tenant,
        status=status_filter,
        start_date=start_date,
        end_date=end_date,
        department=department,
        skip=skip,
        limit=limit,
    )
    return [TransactionResultResponse.model_validate(tx) for tx in rows]


# ---------------------------------------------------------------------------- #
# POST /transactions/request-explanation  — 소명 요청
# ---------------------------------------------------------------------------- #
@router.post(
    "/transactions/request-explanation",
    response_model=list[TransactionResultResponse],
    summary="소명 요청 발송 (-> '요청완료')",
)
def request_explanation(
    payload: ExplanationRequestPayload,
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    admin_id: Annotated[str, Depends(get_admin_id)],
    service: Annotated[ComplianceService, Depends(get_compliance_service)],
) -> list[TransactionResultResponse]:
    """대상 위반 건들에 대해 소명을 요청하고 상태를 '요청완료'로 전이한다.

    요청 ID 중 현재 테넌트 소유가 아닌 건이 섞여 있으면 전체 거부(404).
    """
    try:
        rows = service.request_explanation(tenant, payload, admin_id)
    except ComplianceTransactionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return [TransactionResultResponse.model_validate(tx) for tx in rows]


# ---------------------------------------------------------------------------- #
# POST /transactions/process-explanation  — 소명 처리
# ---------------------------------------------------------------------------- #
@router.post(
    "/transactions/process-explanation",
    response_model=list[TransactionResultResponse],
    summary="소명 처리 (-> '정상처리'/'위반확정')",
)
def process_explanation(
    payload: ExplanationProcessPayload,
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    admin_id: Annotated[str, Depends(get_admin_id)],
    service: Annotated[ComplianceService, Depends(get_compliance_service)],
) -> list[TransactionResultResponse]:
    """소명을 검토해 '정상처리' 또는 '위반확정'으로 종결하고 처리 메타를 기록한다.

    요청 ID 중 현재 테넌트 소유가 아닌 건이 섞여 있으면 전체 거부(404).
    """
    try:
        rows = service.process_explanation(tenant, payload, admin_id)
    except ComplianceTransactionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return [TransactionResultResponse.model_validate(tx) for tx in rows]
