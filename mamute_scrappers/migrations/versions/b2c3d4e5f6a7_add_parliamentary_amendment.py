"""tabela de emendas parlamentares orcamentarias (CS-17)

O Portal da Transparencia nao devolve identificador de parlamentar, so o nome
do autor em texto livre. Por isso `parliamentarian_id` e anulavel e
`match_status` registra explicitamente o resultado do casamento — inclusive o
que nao casou, que precisa ficar visivel para auditoria em vez de ser
descartado silenciosamente.

A FK usa ON DELETE SET NULL, e nao CASCADE como nas demais tabelas ligadas a
parlamentar: a emenda e fato orcamentario publico e nao deve desaparecer se o
parlamentar sair da base.

Volume esperado (medido na fonte em 2026-08-06): ~6 mil linhas por ano,
~31 mil no total de 2022 ate o ano corrente.

Revision ID: b2c3d4e5f6a7
Revises: a9b0c1d2e3f4
Create Date: 2026-08-06 12:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "b2c3d4e5f6a7"
down_revision = "a9b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "parliamentary_amendment",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("amendment_code", sa.Text(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("amendment_number", sa.Text(), nullable=True),
        sa.Column("amendment_type", sa.Text(), nullable=True),
        sa.Column("author_name_raw", sa.Text(), nullable=True),
        sa.Column("author_raw", sa.Text(), nullable=True),
        sa.Column(
            "parliamentarian_id",
            sa.BigInteger(),
            sa.ForeignKey("parliamentarian.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("match_status", sa.Text(), nullable=False),
        sa.Column("spending_locality", sa.Text(), nullable=True),
        sa.Column("function", sa.Text(), nullable=True),
        sa.Column("subfunction", sa.Text(), nullable=True),
        sa.Column("committed_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("settled_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("paid_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("remainder_inscribed", sa.Numeric(18, 2), nullable=True),
        sa.Column("remainder_cancelled", sa.Numeric(18, 2), nullable=True),
        sa.Column("remainder_paid", sa.Numeric(18, 2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_parliamentary_amendment_code",
        "parliamentary_amendment",
        ["amendment_code"],
        unique=True,
    )
    op.create_index(
        "ix_parliamentary_amendment_parliamentarian_year",
        "parliamentary_amendment",
        ["parliamentarian_id", "year"],
    )
    op.create_index(
        "ix_parliamentary_amendment_match_status",
        "parliamentary_amendment",
        ["match_status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_parliamentary_amendment_match_status",
        table_name="parliamentary_amendment",
    )
    op.drop_index(
        "ix_parliamentary_amendment_parliamentarian_year",
        table_name="parliamentary_amendment",
    )
    op.drop_index(
        "ix_parliamentary_amendment_code",
        table_name="parliamentary_amendment",
    )
    op.drop_table("parliamentary_amendment")
