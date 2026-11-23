"""add predefined lead intent

Revision ID: ca2368b8a32f
Revises: a0c9215ed3c0
Create Date: 2026-11-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "ca2368b8a32f"
down_revision: Union[str, Sequence[str], None] = "a0c9215ed3c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("client_requirements", sa.Column("intent", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("client_requirements", "intent")
