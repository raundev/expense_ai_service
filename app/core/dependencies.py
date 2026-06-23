import logging
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.tenant import STATUS_ACTIVE, Tenant

logger = logging.getLogger(__name__)


class TenantContext(BaseModel):
    """멀티테넌트 요청 컨텍스트.

    모든 도메인 접근(용도 규칙, 사칙 RAG, 승인 내역)은 이 컨텍스트를
    기준으로 회사/사업장 범위를 격리한다.
    """

    company_id: str
    workplace_id: str


async def get_tenant_info(
    x_company_id: Annotated[
        str,
        Header(
            alias="X-Company-ID",
            description="요청을 보낸 테넌트(회사) 식별자",
        ),
    ],
    x_workplace_id: Annotated[
        str,
        Header(
            alias="X-Workplace-ID",
            description="요청을 보낸 테넌트(사업장) 식별자",
        ),
    ],
) -> TenantContext:
    """HTTP 헤더에서 멀티테넌트 식별 정보를 추출하는 FastAPI Dependency.

    `X-Company-ID`, `X-Workplace-ID` 헤더가 없으면 FastAPI 가
    자동으로 422 응답을 반환한다.
    """
    return TenantContext(
        company_id=x_company_id,
        workplace_id=x_workplace_id,
    )


async def get_employee_id(
    x_employee_id: Annotated[
        str,
        Header(
            alias="X-Employee-ID",
            description="요청을 보낸 직원(개인) 식별자",
        ),
    ],
) -> str:
    """직원 본인 식별 헤더 추출 (Phase 2, 17단계).

    직원용 소명 API(`/my/transactions`, `submit-explanation`)에서 테넌트 + 본인
    employee_id 로 데이터를 격리하는 데 사용한다. 헤더가 없으면 422.
    """
    return x_employee_id


def require_registered_tenant(
    tenant: Annotated[TenantContext, Depends(get_tenant_info)],
    db: Annotated[Session, Depends(get_db)],
) -> TenantContext:
    """헤더의 (company_id, workplace_id) 가 '등록된 ACTIVE 테넌트' 인지 검증하는 게이트.

    `settings.TENANT_ENFORCEMENT_MODE` 로 동작을 제어한다(점진 롤아웃):
      - "off"     : 검증 없이 통과(기존 동작).
      - "log"     : 미등록이어도 통과하되 경고 로그만 남김(화이트리스트 모니터링 단계).
      - "enforce" : 미등록(또는 SUSPENDED)이면 403.

    반환 타입이 `get_tenant_info` 와 동일한 `TenantContext` 이므로, 도메인 라우터의
    `Depends(get_tenant_info)` 를 건드리지 않고 라우터 레벨 게이트로 얹을 수 있다
    (FastAPI 의존성 캐시로 헤더 추출은 요청당 1회만 실행). DB 접근이 있어 sync 로 두어
    스레드풀에서 실행되게 한다(이벤트 루프 블로킹 방지).
    """
    mode = settings.TENANT_ENFORCEMENT_MODE
    if mode == "off":
        return tenant

    registered = db.scalar(
        select(Tenant.id).where(
            Tenant.company_id == tenant.company_id,
            Tenant.workplace_id == tenant.workplace_id,
            Tenant.status == STATUS_ACTIVE,
        )
    )
    if registered is not None:
        return tenant

    # 미등록 또는 SUSPENDED.
    if mode == "log":
        logger.warning(
            "미등록 테넌트 접근(통과: log 모드): company_id=%s workplace_id=%s",
            tenant.company_id, tenant.workplace_id,
        )
        return tenant

    logger.warning(
        "미등록 테넌트 접근 차단: company_id=%s workplace_id=%s",
        tenant.company_id, tenant.workplace_id,
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="등록되지 않은 테넌트입니다. 관리자에게 (company_id, workplace_id) 등록을 요청하세요.",
    )
