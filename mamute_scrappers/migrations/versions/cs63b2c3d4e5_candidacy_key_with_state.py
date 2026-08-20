"""candidacy: chave natural passa a incluir a UF

Revision ID: cs63b2c3d4e5
Revises: cs63a1b2c3d4
Create Date: 2026-08-20

CS-63: nos CSVs de dados abertos de 2002 e 2006 o SQ_CANDIDATO e sequencial
POR UF (medido ao vivo: o "119" de 2002 existe em 26 estados, pessoas
diferentes), entao (election_year, tse_candidate_id) colide na carga
historica. De 2010 em diante — e na DivulgaCandContas de 2026 — o id e
globalmente unico e a UF na chave nao muda nada.

A base atual (so 2026) satisfaz a constraint nova por construcao.
"""

from alembic import op

revision = "cs63b2c3d4e5"
down_revision = "cs63a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A chave original nasceu como INDICE unico (c4d5e6f7a8b9), nao constraint.
    op.drop_index("uq_candidacy_election_tse_id", table_name="candidacy")
    op.create_index(
        "uq_candidacy_election_state_tse_id",
        "candidacy",
        ["election_year", "state", "tse_candidate_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_candidacy_election_state_tse_id", table_name="candidacy")
    op.create_index(
        "uq_candidacy_election_tse_id",
        "candidacy",
        ["election_year", "tse_candidate_id"],
        unique=True,
    )
