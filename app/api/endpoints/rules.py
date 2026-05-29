from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import TenantContext, get_tenant_info
from app.db.session import get_db
from app.schemas.rules import RuleRequest, RuleResponse
from app.services.rule_service import RuleNotFoundError, RuleService

router = APIRouter()


# ---------------------------------------------------------------------------- #
# GET /  — 규칙 목록 조회
# ---------------------------------------------------------------------------- #
@router.get(
    "/",
    response_model=list[RuleResponse],
    summary="활성 규칙 목록 조회 (테넌트 격리)",
)
def list_active_rules(
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    db: Annotated[Session, Depends(get_db)],
) -> list[RuleResponse]:
    """`X-Company-ID` / `X-Workplace-ID` 헤더 기준으로 활성 규칙을 조회한다.

    회사 공통 규칙(workplace_id=NULL) 과 사업장 전용 규칙을 모두 포함하며
    `priority` 오름차순으로 정렬된다.
    """
    service = RuleService(db)
    rules = service.get_active_rules(tenant)
    return [RuleResponse.model_validate(rule) for rule in rules]


# ---------------------------------------------------------------------------- #
# POST /create  — 규칙 신규 등록
# ---------------------------------------------------------------------------- #
@router.post(
    "/create",
    response_model=RuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="신규 분류 규칙 등록",
)
def create_rule(
    payload: RuleRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    db: Annotated[Session, Depends(get_db)],
) -> RuleResponse:
    """규칙을 새로 생성한다.

    `company_id` / `workplace_id` 는 요청 헤더에서 자동 주입되므로 Body 에서 받지 않는다.
    """
    service = RuleService(db)
    rule = service.create_rule(payload, tenant)
    return RuleResponse.model_validate(rule)


# ---------------------------------------------------------------------------- #
# PUT /update/{rule_id}  — 기존 규칙 수정
# ---------------------------------------------------------------------------- #
@router.put(
    "/update/{rule_id}",
    response_model=RuleResponse,
    summary="기존 분류 규칙 수정",
)
def update_rule(
    rule_id: int,
    payload: RuleRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    db: Annotated[Session, Depends(get_db)],
) -> RuleResponse:
    """`rule_id` 의 규칙을 수정한다.

    권한 검증: 헤더의 (company_id, workplace_id) 가 모두 일치하는 본인 테넌트의
    규칙만 수정 가능하며, 그렇지 않으면 404 를 반환한다(타 테넌트 데이터의
    존재 여부 자체를 노출하지 않기 위해 403 이 아닌 404 로 통일).
    """
    service = RuleService(db)
    try:
        rule = service.update_rule(rule_id, payload, tenant)
    except RuleNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return RuleResponse.model_validate(rule)
