"""tabela de candidaturas eleitorais do TSE (CS-16)

Candidaturas da Eleicao Geral coletadas da DivulgaCandContas, uma linha por
candidatura por eleicao, chaveada por (election_year, tse_candidate_id).

`parliamentarian_id` e anulavel com ON DELETE SET NULL: a maioria dos ~29 mil
candidatos de 2026 nao e parlamentar em exercicio, e candidatura e fato
publico que nao deve sumir se o parlamentar sair da base — mesma decisao da
tabela de emendas. `match_status` registra o resultado do casamento
(matched_cpf / matched_name / ambiguous / unmatched / manual), inclusive o que
nao casou, visivel para auditoria.

`listing_fingerprint` e o hash dos campos da listagem da DivulgaCandContas; so
e gravado quando o detalhe do candidato foi lido com sucesso, de modo que
falha de detalhe forca nova tentativa na execucao seguinte.

Volume esperado (medido na fonte em 2026-08-07): ~29 mil candidaturas titulares
na eleicao de 2026.

Revision ID: c4d5e6f7a8b9
Revises: b2c3d4e5f6a7
Create Date: 2026-08-08 12:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "c4d5e6f7a8b9"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candidacy",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("election_year", sa.Integer(), nullable=False),
        sa.Column("tse_candidate_id", sa.BigInteger(), nullable=False),
        sa.Column("office_code", sa.Integer(), nullable=True),
        sa.Column("office", sa.Text(), nullable=True),
        sa.Column("state", sa.Text(), nullable=True),
        sa.Column("ballot_number", sa.Integer(), nullable=True),
        sa.Column("ballot_name", sa.Text(), nullable=True),
        sa.Column("full_name", sa.Text(), nullable=True),
        sa.Column("party", sa.Text(), nullable=True),
        sa.Column("coalition", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("totalization_status", sa.Text(), nullable=True),
        sa.Column("cpf", sa.Text(), nullable=True),
        sa.Column("voter_id", sa.Text(), nullable=True),
        sa.Column("photo_url", sa.Text(), nullable=True),
        sa.Column("tse_last_update", sa.DateTime(), nullable=True),
        sa.Column("listing_fingerprint", sa.Text(), nullable=True),
        sa.Column(
            "parliamentarian_id",
            sa.BigInteger(),
            sa.ForeignKey("parliamentarian.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("match_status", sa.Text(), nullable=False),
        sa.Column("details", JSONB(), nullable=True),
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
        "uq_candidacy_election_tse_id",
        "candidacy",
        ["election_year", "tse_candidate_id"],
        unique=True,
    )
    op.create_index("ix_candidacy_state", "candidacy", ["state"])
    op.create_index("ix_candidacy_office_code", "candidacy", ["office_code"])
    op.create_index("ix_candidacy_match_status", "candidacy", ["match_status"])
    op.create_index(
        "ix_candidacy_parliamentarian_id", "candidacy", ["parliamentarian_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_candidacy_parliamentarian_id", table_name="candidacy")
    op.drop_index("ix_candidacy_match_status", table_name="candidacy")
    op.drop_index("ix_candidacy_office_code", table_name="candidacy")
    op.drop_index("ix_candidacy_state", table_name="candidacy")
    op.drop_index("uq_candidacy_election_tse_id", table_name="candidacy")
    op.drop_table("candidacy")
