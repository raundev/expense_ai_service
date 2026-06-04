from typing import Annotated

from fastapi import Header
from pydantic import BaseModel


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
