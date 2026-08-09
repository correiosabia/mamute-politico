"""tabela de timeline eleitoral com patrimonio (CS-54)

Linha do tempo eleitoral por pessoa x eleicao x cargo, semeada do campo
`eleicoesAnteriores` que a DivulgaCandContas devolve no detalhe de cada
candidatura (ja armazenado em candidacy.details para 100% das candidaturas
2026). Chave natural (election_year, tse_candidate_id) — o id do candidato
muda a cada eleicao; o vinculo estavel e parliamentarian_id/candidacy_id.

`assets_fetched_at` NULL = patrimonio (bens declarados) pendente de busca no
detalhe daquele ano; o cron drena incrementalmente, e falha de detalhe se
auto-corrige na execucao seguinte — mesmo desenho do fingerprint da candidacy.

Volume esperado: ~30-50 mil linhas (8.5 mil candidatos 2026 com historico
previo, medido em producao em 2026-08-09, mais os ~200 parlamentares sem
candidatura 2026).

Revision ID: e6f7a8b9c0d1
Revises: c4d5e6f7a8b9
Create Date: 2026-08-09 21:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "e6f7a8b9c0d1"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "electoral_history",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("election_year", sa.Integer(), nullable=False),
        sa.Column("tse_candidate_id", sa.BigInteger(), nullable=False),
        sa.Column("tse_election_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "parliamentarian_id",
            sa.BigInteger(),
            sa.ForeignKey("parliamentarian.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "candidacy_id",
            sa.BigInteger(),
            sa.ForeignKey("candidacy.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("office", sa.Text(), nullable=True),
        sa.Column("state", sa.Text(), nullable=True),
        sa.Column("locality", sa.Text(), nullable=True),
        sa.Column("party", sa.Text(), nullable=True),
        sa.Column("ballot_name", sa.Text(), nullable=True),
        sa.Column("full_name", sa.Text(), nullable=True),
        sa.Column("ballot_number", sa.Integer(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("declared_assets", sa.Numeric(18, 2), nullable=True),
        sa.Column("assets_count", sa.Integer(), nullable=True),
        sa.Column("assets", JSONB(), nullable=True),
        sa.Column("assets_fetched_at", sa.DateTime(), nullable=True),
        sa.Column("source_link", sa.Text(), nullable=True),
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
        "uq_electoral_history_year_tse_id",
        "electoral_history",
        ["election_year", "tse_candidate_id"],
        unique=True,
    )
    op.create_index(
        "ix_electoral_history_parliamentarian_id",
        "electoral_history",
        ["parliamentarian_id"],
    )
    op.create_index(
        "ix_electoral_history_candidacy_id",
        "electoral_history",
        ["candidacy_id"],
    )
    op.create_index(
        "ix_electoral_history_election_year",
        "electoral_history",
        ["election_year"],
    )


def downgrade() -> None:
    op.drop_index("ix_electoral_history_election_year", table_name="electoral_history")
    op.drop_index("ix_electoral_history_candidacy_id", table_name="electoral_history")
    op.drop_index(
        "ix_electoral_history_parliamentarian_id", table_name="electoral_history"
    )
    op.drop_index("uq_electoral_history_year_tse_id", table_name="electoral_history")
    op.drop_table("electoral_history")
