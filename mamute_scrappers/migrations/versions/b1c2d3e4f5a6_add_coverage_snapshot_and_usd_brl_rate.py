"""add coverage_snapshot + usd_brl_rate (caches diários dos painéis admin)

coverage_snapshot: guarda o resultado já computado da cobertura do banco
(pesado de calcular ao vivo) como um único JSON, atualizado 1x/dia pela rotina
mamute_scrappers.scripts.refresh_admin_caches. A API só lê a linha mais recente.

usd_brl_rate: cotação USD→BRL do dia (uma linha por data), preenchida pela mesma
rotina via API pública. A API lê a linha mais recente em vez de usar um valor
fixo desatualizado.

Também cria índice (source, year) em api_coverage para o SUM por ano.

Revision ID: b1c2d3e4f5a6
Revises: a7b8c9d0e1f2
Create Date: 2026-07-05 20:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "b1c2d3e4f5a6"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "coverage_snapshot",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "usd_brl_rate",
        sa.Column("rate_date", sa.Date(), primary_key=True),
        sa.Column("bid", sa.Numeric(12, 6), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_api_coverage_source_year",
        "api_coverage",
        ["source", "year"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_api_coverage_source_year", table_name="api_coverage")
    op.drop_table("usd_brl_rate")
    op.drop_table("coverage_snapshot")
