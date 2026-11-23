"""generalize property locations and currencies

Revision ID: b817a91a52e0
Revises: ca2368b8a32f
Create Date: 2026-11-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b817a91a52e0"
down_revision: Union[str, Sequence[str], None] = "ca2368b8a32f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("client_requirements", sa.Column("country", sa.String(), nullable=True))
    op.add_column("client_requirements", sa.Column("city_region", sa.String(), nullable=True))
    op.add_column(
        "client_requirements",
        sa.Column(
            "preferred_locations",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
    )
    op.add_column("client_requirements", sa.Column("budget_min", sa.BigInteger(), nullable=True))
    op.add_column("client_requirements", sa.Column("budget_max", sa.BigInteger(), nullable=True))
    op.add_column("client_requirements", sa.Column("budget_currency", sa.String(length=3), nullable=True))
    op.add_column("client_portfolio_items", sa.Column("estimated_value", sa.BigInteger(), nullable=True))
    op.add_column("client_portfolio_items", sa.Column("estimated_value_currency", sa.String(length=3), nullable=True))

    op.execute("""
        UPDATE client_requirements
        SET country = CASE WHEN emirate IS NOT NULL THEN 'United Arab Emirates' ELSE NULL END,
            city_region = emirate,
            preferred_locations = COALESCE(preferred_communities, '{}'::varchar[]),
            budget_min = budget_min_aed,
            budget_max = budget_max_aed,
            budget_currency = CASE WHEN budget_max_aed IS NOT NULL OR budget_min_aed IS NOT NULL THEN 'AED' ELSE NULL END
    """)
    op.execute("""
        UPDATE client_portfolio_items
        SET estimated_value = estimated_value_aed,
            estimated_value_currency = CASE WHEN estimated_value_aed IS NOT NULL THEN 'AED' ELSE NULL END
    """)


def downgrade() -> None:
    op.drop_column("client_portfolio_items", "estimated_value_currency")
    op.drop_column("client_portfolio_items", "estimated_value")
    op.drop_column("client_requirements", "budget_currency")
    op.drop_column("client_requirements", "budget_max")
    op.drop_column("client_requirements", "budget_min")
    op.drop_column("client_requirements", "preferred_locations")
    op.drop_column("client_requirements", "city_region")
    op.drop_column("client_requirements", "country")
