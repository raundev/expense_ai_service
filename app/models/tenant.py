"""테넌트(회사/사업장) 화이트리스트 모델 — 미등록 ID 의 데이터 생성/접근 차단용.

도메인 데이터(봇·문서·규칙·거래 등)는 헤더의 `(company_id, workplace_id)` 로 격리되지만,
그 값이 '등록된' 테넌트인지는 검증하지 않았다. 이 테이블은 허용된 (회사, 사업장) 조합의
화이트리스트이며, `require_registered_tenant` 의존성(app/core/dependencies.py)이 매 요청
이 테이블로 검증한다.

PK 는 다른 모델과 동일하게 String(36) UUID(uuid4, 앱 생성)로 통일한다(설계 D4).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _uuid() -> str:
    """앱 레벨 UUID(uuid4) 생성기. SQLite/PostgreSQL 양쪽 호환 String(36) PK."""
    return str(uuid.uuid4())


# 테넌트 상태값. SUSPENDED 는 등록돼 있어도 차단한다(일시 정지).
STATUS_ACTIVE = "ACTIVE"
STATUS_SUSPENDED = "SUSPENDED"


class Tenant(Base):
    """등록된 (회사, 사업장) 화이트리스트 1건."""

    __tablename__ = "tenants"
    __table_args__ = (
        # (회사, 사업장) 조합은 유일하다.
        UniqueConstraint("company_id", "workplace_id", name="uq_tenant_company_workplace"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    # --- 테넌트 식별 (검증 키) ---
    company_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    workplace_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    # --- 표시용(선택) ---
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    workplace_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # "ACTIVE" | "SUSPENDED" — SUSPENDED 는 검증에서 차단.
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=STATUS_ACTIVE, server_default=text("'ACTIVE'")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Tenant id={self.id!r} company_id={self.company_id!r} "
            f"workplace_id={self.workplace_id!r} status={self.status!r}>"
        )
