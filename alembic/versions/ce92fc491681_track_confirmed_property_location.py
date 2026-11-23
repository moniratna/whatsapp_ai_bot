"""track customer-confirmed property locations

Revision ID: ce92fc491681
Revises: b817a91a52e0
Create Date: 2026-11-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "ce92fc491681"
down_revision: Union[str, Sequence[str], None] = "b817a91a52e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "client_requirements",
        sa.Column(
            "location_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("client_requirements", "location_confirmed")
