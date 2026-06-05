"""merge multihead (llm_suggested + phase2)

Revision ID: c154a0912972
Revises: 69bc67fd2582, ca1bb214fb35
Create Date: 2026-06-05 14:10:24.263405

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c154a0912972'
down_revision: Union[str, Sequence[str], None] = ('69bc67fd2582', 'ca1bb214fb35')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
