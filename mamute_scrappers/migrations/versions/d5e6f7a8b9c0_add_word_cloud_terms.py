"""termos de filtro da nuvem de palavras, geridos pelo painel admin

A lista vivia fixa em ui/src/components/dashboard/WordCloud.tsx, então qualquer
ajuste exigia deploy da UI. Passa para o banco, editável em Configurações gerais.

O seed traz exatamente o que a lista fixa já filtrava, mais "parlamentar" e
"gente" — pedidos pelo cliente. Sem esse seed a nuvem regrediria no deploy, já
que a lista fixa sai do código no mesmo commit.

Revision ID: d5e6f7a8b9c0
Revises: c3d4e5f6a7b8
Create Date: 2026-07-29 03:10:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "d5e6f7a8b9c0"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


# Espelha a constante STOPWORDS que sai do WordCloud.tsx neste mesmo commit.
SEED_STOPWORDS = [
    "a", "ao", "aos", "aprovação", "aprovamos", "as", "até", "com", "da", "das",
    "de", "do", "dos", "durante", "e", "em", "na", "nas", "no", "nos", "o",
    "obrigado", "os", "para", "pec", "pela", "pelas", "pelo", "pelos", "por",
    "presidente", "projeto", "que", "relator", "sem", "senador", "senadora",
    "sessão", "sob", "sobre", "um", "uma",
    # Pedidos do cliente (jul/2026).
    "gente", "parlamentar",
]


def upgrade() -> None:
    op.create_table(
        "word_cloud_terms",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("term", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
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
        sa.UniqueConstraint("term", "kind", name="uq_word_cloud_terms_term_kind"),
    )
    op.create_index(
        "ix_word_cloud_terms_kind", "word_cloud_terms", ["kind"], unique=False
    )

    tabela = sa.table(
        "word_cloud_terms",
        sa.column("term", sa.Text),
        sa.column("kind", sa.Text),
    )
    op.bulk_insert(
        tabela,
        [{"term": termo, "kind": "stopword"} for termo in sorted(set(SEED_STOPWORDS))],
    )


def downgrade() -> None:
    op.drop_index("ix_word_cloud_terms_kind", table_name="word_cloud_terms")
    op.drop_table("word_cloud_terms")
