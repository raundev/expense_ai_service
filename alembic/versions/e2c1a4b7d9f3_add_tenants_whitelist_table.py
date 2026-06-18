"""add tenants whitelist table (+ backfill existing distinct company/workplace pairs)

미등록 (company_id, workplace_id) 의 도메인 데이터 생성/접근을 차단하기 위한 화이트리스트
테이블을 추가한다. 운영 중 데이터가 'unregistered' 로 분류되지 않도록, 기존 도메인 테이블의
distinct (company_id, workplace_id) 조합을 ACTIVE 로 백필한다.

Revision ID: e2c1a4b7d9f3
Revises: d5617aa3741a
Create Date: 2026-06-08 09:00:00.000000

"""
import uuid
from datetime import datetime
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e2c1a4b7d9f3'
down_revision: Union[str, Sequence[str], None] = 'd5617aa3741a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 백필 후보: company_id + workplace_id 를 모두 가진 기존 도메인 테이블.
# (실제 컬럼 보유 여부는 introspection 으로 재확인하므로 환경/테이블명 차이에 안전하다.)
_BACKFILL_TABLES = (
    "bots",
    "documents",
    "chat_sessions",
    "approval_history",
    "company_receipt_rules",
    "receipt_transactions",
    "receipt_files",
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=64), nullable=False),
        sa.Column("workplace_id", sa.String(length=64), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("workplace_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'ACTIVE'"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "workplace_id", name="uq_tenant_company_workplace"),
    )
    op.create_index(op.f("ix_tenants_company_id"), "tenants", ["company_id"], unique=False)
    op.create_index(op.f("ix_tenants_workplace_id"), "tenants", ["workplace_id"], unique=False)

    _backfill_existing_tenants()


def _backfill_existing_tenants() -> None:
    """기존 도메인 테이블의 distinct (company_id, workplace_id) 를 tenants 로 적재."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    pairs = set()
    for table in _BACKFILL_TABLES:
        if table not in existing:
            continue
        cols = {c["name"] for c in inspector.get_columns(table)}
        if not {"company_id", "workplace_id"} <= cols:
            continue
        rows = bind.execute(
            sa.text(f"SELECT DISTINCT company_id, workplace_id FROM {table}")
        ).fetchall()
        for company_id, workplace_id in rows:
            # workplace_id 가 NULL 인 행(예: 회사 단위 규칙)은 테넌트 쌍을 만들 수 없어 제외.
            if company_id and workplace_id:
                pairs.add((company_id, workplace_id))

    if not pairs:
        return

    now = datetime.utcnow()
    tenants_tbl = sa.table(
        "tenants",
        sa.column("id", sa.String),
        sa.column("company_id", sa.String),
        sa.column("workplace_id", sa.String),
        sa.column("company_name", sa.String),
        sa.column("workplace_name", sa.String),
        sa.column("status", sa.String),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    op.bulk_insert(
        tenants_tbl,
        [
            {
                "id": str(uuid.uuid4()),
                "company_id": company_id,
                "workplace_id": workplace_id,
                "company_name": None,
                "workplace_name": None,
                "status": "ACTIVE",
                "created_at": now,
                "updated_at": now,
            }
            for (company_id, workplace_id) in sorted(pairs)
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_tenants_workplace_id"), table_name="tenants")
    op.drop_index(op.f("ix_tenants_company_id"), table_name="tenants")
    op.drop_table("tenants")
