"""add candidacy demographic profile

Revision ID: cs63a1b2c3d4
Revises: c9d0e1f2a3b4
Create Date: 2026-08-20

CS-63: metricas de perfil demografico dos candidatos (cor/raca, genero,
escolaridade, ocupacao, estado civil, nascimento, nacionalidade, federacao)
como colunas tipadas na candidacy. Para 2026 os valores ja existem no JSONB
`details` (detalhe da DivulgaCandContas) e sao promovidos por script; o
historico 1994->2022 entra pelos CSVs de dados abertos do TSE (consulta_cand).

Valores normalizados em MAIUSCULAS na forma dos CSVs para agregacao cruzada.
Cor/raca so e coletada pelo TSE desde 2014 e federacao desde 2022 — NULL
antes disso e lacuna da fonte. `profile_source` distingue 'divulgacand'
(API, so 2026) de 'tse_csv' (dados abertos); o CSV nunca sobrescreve campo
preenchido pela API, so completa NULL.

Indices parciais por ano ja existem (election_year); agregacoes demograficas
futuras (task propria) decidirao indices adicionais com a consulta na mao.
"""

from alembic import op
import sqlalchemy as sa

revision = "cs63a1b2c3d4"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None

_PROFILE_TEXT_COLUMNS = (
    "gender",
    "race",
    "education",
    "occupation",
    "marital_status",
    "nationality",
    "federation",
    "profile_source",
)


def upgrade() -> None:
    op.add_column("candidacy", sa.Column("birth_date", sa.Date(), nullable=True))
    for name in _PROFILE_TEXT_COLUMNS:
        op.add_column("candidacy", sa.Column(name, sa.Text(), nullable=True))


def downgrade() -> None:
    for name in reversed(_PROFILE_TEXT_COLUMNS):
        op.drop_column("candidacy", name)
    op.drop_column("candidacy", "birth_date")
