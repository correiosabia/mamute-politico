"""add api_coverage table (contagens das APIs abertas p/ comparar cobertura)

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-05 18:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_coverage",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source", sa.Text(), nullable=False),  # camara | senado
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("sigla_type", sa.Text(), nullable=True),
        sa.Column("api_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("source", "year", "sigla_type", name="uq_api_coverage_key"),
    )
    op.create_index(op.f("ix_api_coverage_id"), "api_coverage", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_api_coverage_id"), table_name="api_coverage")
    op.drop_table("api_coverage")
