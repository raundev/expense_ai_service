import csv
import io
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.dependencies import TenantContext, get_employee_id, get_tenant_info
from app.db.session import get_db
from app.schemas.compliance import (
    DashboardChartsResponse,
    DashboardKpiResponse,
    ExplanationCancelPayload,
    ExplanationProcessPayload,
    ExplanationRequestPayload,
    ExplanationSubmitPayload,
)
from app.schemas.transactions import TransactionResultResponse
from app.services.compliance_service import (
    ComplianceInvalidStateError,
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
    except ComplianceInvalidStateError as exc:
        # 처리 가능 상태(요청완료/소명제출/기한초과)가 아닌 건 포함 시 409
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return [TransactionResultResponse.model_validate(tx) for tx in rows]


# ---------------------------------------------------------------------------- #
# POST /transactions/cancel-explanation  — 소명 요청 취소 (PRD 5.3)
# ---------------------------------------------------------------------------- #
@router.post(
    "/transactions/cancel-explanation",
    response_model=list[TransactionResultResponse],
    summary="소명 요청 취소 (-> '미요청' 롤백)",
)
def cancel_explanation(
    payload: ExplanationCancelPayload,
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    admin_id: Annotated[str, Depends(get_admin_id)],
    service: Annotated[ComplianceService, Depends(get_compliance_service)],
) -> list[TransactionResultResponse]:
    """'요청완료' 상태인 소명 요청을 취소해 '미요청'으로 되돌리고 요청 메타를 초기화한다.

    - 미소유 ID 포함 시 전체 거부(404)
    - '요청완료' 가 아닌 건 포함 시 전체 거부(409 Conflict)
    """
    try:
        rows = service.cancel_explanation(tenant, payload, admin_id)
    except ComplianceTransactionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except ComplianceInvalidStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return [TransactionResultResponse.model_validate(tx) for tx in rows]


# ---------------------------------------------------------------------------- #
# GET /dashboard/charts  — 시각화 차트 데이터 (PRD 5.1)
# ---------------------------------------------------------------------------- #
@router.get(
    "/dashboard/charts",
    response_model=DashboardChartsResponse,
    summary="대시보드 시각화 차트 데이터 (일별 추이/항목별/부서별)",
)
def get_dashboard_charts(
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    service: Annotated[ComplianceService, Depends(get_compliance_service)],
    start_date: Annotated[date | None, Query(description="영수증 일자 시작(YYYY-MM-DD)")] = None,
    end_date: Annotated[date | None, Query(description="영수증 일자 종료(YYYY-MM-DD)")] = None,
    department: Annotated[str | None, Query(description="부서 필터")] = None,
) -> DashboardChartsResponse:
    """기간/부서 조건으로 위반 데이터를 GROUP BY 집계한 시각화용 데이터를 반환한다."""
    charts = service.get_dashboard_charts(tenant, start_date, end_date, department)
    return DashboardChartsResponse(**charts)


# ---------------------------------------------------------------------------- #
# GET /transactions/export  — 위반 그리드 엑셀(CSV) 다운로드 (PRD 5.2)
# ---------------------------------------------------------------------------- #
_EXPORT_HEADERS = [
    "거래ID", "사용일시", "부서", "가맹점명", "금액",
    "용도", "위반사유", "소명상태", "소명요청자", "소명처리자",
]


@router.get(
    "/transactions/export",
    summary="위반 영수증 엑셀(CSV) 다운로드 (필터 동일, 페이지네이션 없음)",
)
def export_violations(
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    service: Annotated[ComplianceService, Depends(get_compliance_service)],
    status_filter: Annotated[
        str | None, Query(alias="status", description="소명 상태 필터")
    ] = None,
    start_date: Annotated[date | None, Query(description="영수증 일자 시작(YYYY-MM-DD)")] = None,
    end_date: Annotated[date | None, Query(description="영수증 일자 종료(YYYY-MM-DD)")] = None,
    department: Annotated[str | None, Query(description="부서 필터")] = None,
) -> StreamingResponse:
    """그리드와 동일 필터로 전체 위반을 조회해 CSV 스트림으로 다운로드한다.

    Excel 한글 깨짐 방지를 위해 UTF-8 BOM 을 선두에 붙인다.
    """
    rows = service.get_violations_for_export(
        tenant=tenant,
        status=status_filter,
        start_date=start_date,
        end_date=end_date,
        department=department,
    )
    # 세션 의존을 끊기 위해 응답 직렬화 전에 평문 행으로 추출.
    data = [
        [
            tx.id,
            f"{tx.receipt_date} {tx.receipt_time}",
            tx.department or "",
            tx.merchant_name,
            tx.amount,
            tx.recommended_result_category,
            tx.violation_reason or "",
            tx.explanation_status or "",
            tx.explanation_requester or "",
            tx.explanation_processor or "",
        ]
        for tx in rows
    ]

    def _stream():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        buffer.write("﻿")  # UTF-8 BOM (Excel 한글 깨짐 방지)
        writer.writerow(_EXPORT_HEADERS)
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        for row in data:
            writer.writerow(row)
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)

    return StreamingResponse(
        _stream(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="compliance_violations.csv"'},
    )


# ---------------------------------------------------------------------------- #
# 직원용 소명 워크플로우 (Phase 2, 17단계)
# ---------------------------------------------------------------------------- #
@router.get(
    "/my/transactions",
    response_model=list[TransactionResultResponse],
    summary="내 위반/소명 대상 영수증 조회 (직원 본인)",
)
def list_my_violations(
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    employee_id: Annotated[str, Depends(get_employee_id)],
    service: Annotated[ComplianceService, Depends(get_compliance_service)],
    status_filter: Annotated[
        str | None, Query(alias="status", description="소명 상태 필터(요청완료/소명제출 등)")
    ] = None,
    skip: Annotated[int, Query(ge=0, description="페이지네이션 offset")] = 0,
    limit: Annotated[int, Query(ge=1, le=200, description="페이지 크기")] = 50,
) -> list[TransactionResultResponse]:
    """로그인 직원(`X-Employee-ID`) **본인**의 위반/소명 대상 영수증만 반환한다.

    (company_id, workplace_id, employee_id) 3중 격리 — 타인 건은 노출되지 않는다.
    """
    rows = service.get_my_violations(
        tenant=tenant,
        employee_id=employee_id,
        status=status_filter,
        skip=skip,
        limit=limit,
    )
    return [TransactionResultResponse.model_validate(tx) for tx in rows]


@router.post(
    "/transactions/{transaction_id}/submit-explanation",
    response_model=TransactionResultResponse,
    summary="소명 제출 (직원 본인, '요청완료' -> '소명제출')",
)
def submit_explanation(
    transaction_id: int,
    payload: ExplanationSubmitPayload,
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    employee_id: Annotated[str, Depends(get_employee_id)],
    service: Annotated[ComplianceService, Depends(get_compliance_service)],
) -> TransactionResultResponse:
    """직원이 본인 위반 건에 소명 내용을 제출한다.

    - 본인(`X-Employee-ID`)·테넌트 소유가 아닌 건이면 404 (존재 비노출)
    - 현재 상태가 '요청완료' 가 아니면 409 (잘못된 전이)
    """
    try:
        tx = service.submit_explanation(
            tenant=tenant,
            transaction_id=transaction_id,
            employee_id=employee_id,
            content=payload.content,
        )
    except ComplianceTransactionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except ComplianceInvalidStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return TransactionResultResponse.model_validate(tx)
