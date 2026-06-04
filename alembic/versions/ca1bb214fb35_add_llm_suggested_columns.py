"""add_llm_suggested_columns

Revision ID: ca1bb214fb35
Revises: 7d2164854de5
Create Date: 2026-06-04 09:28:42.594428

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ca1bb214fb35'
down_revision: Union[str, Sequence[str], None] = '7d2164854de5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # LLM off-list 자유 제안(selection=0) 스냅샷. 배치 적재 시에만 채워지는 nullable 컬럼.
    op.add_column('receipt_transactions', sa.Column('llm_suggested_code', sa.String(length=64), nullable=True))
    op.add_column('receipt_transactions', sa.Column('llm_suggested_name', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('receipt_transactions', 'llm_suggested_name')
    op.drop_column('receipt_transactions', 'llm_suggested_code')
