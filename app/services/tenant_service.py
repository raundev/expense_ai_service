"""테넌트 화이트리스트 도메인 서비스.

등록(register) / 목록(list) / 상태·표시명 수정(update). 요청 경로의 등록 검증 자체는
`require_registered_tenant` 의존성(app/core/dependencies.py)이 수행하므로, 이 서비스는
화이트리스트 관리(admin)만 담당한다. DB 전용(LLM 미사용).
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tenant import STATUS_ACTIVE, Tenant
from app.schemas.tenants import TenantCreateRequest, TenantUpdateRequest

logger = logging.getLogger(__name__)


class TenantAlreadyExistsError(Exception):
    """동일 (company_id, workplace_id) 가 이미 등록돼 있을 때(409)."""

    def __init__(self, company_id: str, workplace_id: str) -> None:
        self.company_id = company_id
        self.workplace_id = workplace_id
        super().__init__(f"tenant already exists: {company_id}/{workplace_id}")


class TenantNotFoundError(Exception):
    """대상 테넌트를 찾을 수 없을 때(404)."""

    def __init__(self, tenant_id: str) -> None:
        self.tenant_id = tenant_id
        super().__init__(f"tenant not found: {tenant_id}")


class TenantService:
    """테넌트 화이트리스트 CRUD 서비스."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def register(self, payload: TenantCreateRequest) -> Tenant:
        """테넌트 등록. (company_id, workplace_id) 중복 시 TenantAlreadyExistsError(409)."""
        exists = self.db.scalar(
            select(Tenant.id).where(
                Tenant.company_id == payload.company_id,
                Tenant.workplace_id == payload.workplace_id,
            )
        )
        if exists is not None:
            raise TenantAlreadyExistsError(payload.company_id, payload.workplace_id)

        tenant = Tenant(
            company_id=payload.company_id,
            workplace_id=payload.workplace_id,
            company_name=payload.company_name,
            workplace_name=payload.workplace_name,
            status=STATUS_ACTIVE,
        )
        self.db.add(tenant)
        self.db.commit()
        self.db.refresh(tenant)
        logger.info(
            "테넌트 등록: %s/%s id=%s",
            tenant.company_id, tenant.workplace_id, tenant.id,
        )
        return tenant

    def list_tenants(self) -> list[Tenant]:
        """전체 테넌트 목록(company_id, workplace_id ASC)."""
        stmt = select(Tenant).order_by(
            Tenant.company_id.asc(), Tenant.workplace_id.asc()
        )
        return list(self.db.execute(stmt).scalars().all())

    def update(self, tenant_id: str, payload: TenantUpdateRequest) -> Tenant:
        """상태/표시명 수정. 없으면 TenantNotFoundError(404).

        PATCH 시맨틱 — model_dump(exclude_unset=True) 로 '미전달' 과 'null 명시' 를 구분한다.
        """
        tenant = self.db.get(Tenant, tenant_id)
        if tenant is None:
            raise TenantNotFoundError(tenant_id)

        data = payload.model_dump(exclude_unset=True)
        if data.get("status") is not None:
            tenant.status = data["status"]
        if "company_name" in data:
            tenant.company_name = data["company_name"]
        if "workplace_name" in data:
            tenant.workplace_name = data["workplace_name"]
        self.db.commit()
        self.db.refresh(tenant)
        logger.info("테넌트 수정: id=%s status=%s", tenant.id, tenant.status)
        return tenant
