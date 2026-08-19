"""add parliamentary_expense

Revision ID: c9d0e1f2a3b4
Revises: b8f4d2a91c57
Create Date: 2026-08-19

CS-57: gastos da cota parlamentar (CEAP da Camara + CEAPS do Senado), uma
linha por despesa, discriminada por `house`. Chave natural (house, source_key)
para upsert idempotente: ideDocumento no CSV anual da Camara, id da API de
dados abertos no Senado, hash deterministico quando a Camara nao publica id.

Volume medido na fonte em 2026-08-19: ~208 mil linhas/ano na Camara e ~24 mil
no Senado; com o recorte 2022->hoje a tabela fica em ~1 milhao de linhas, e o
indice composto (parliamentarian_id, year) atende as consultas do perfil.

Sem seed de feature flag: `cota_parlamentar` nasce off e oculta nos planos,
convencao do projeto desde 2026-08-19.
"""

from alembic import op
import sqlalchemy as sa

revision = "c9d0e1f2a3b4"
down_revision = "b8f4d2a91c57"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "parliamentary_expense",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("house", sa.Text(), nullable=False),
        sa.Column("source_key", sa.Text(), nullable=False),
        sa.Column(
            "parliamentarian_id",
            sa.BigInteger(),
            sa.ForeignKey("parliamentarian.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("expense_type", sa.Text(), nullable=False),
        sa.Column("supplier_name", sa.Text()),
        sa.Column("supplier_id", sa.Text()),
        sa.Column("document_number", sa.Text()),
        sa.Column("document_date", sa.Date()),
        sa.Column("details", sa.Text()),
        sa.Column("document_value", sa.Numeric(18, 2)),
        sa.Column("glosa_value", sa.Numeric(18, 2)),
        sa.Column("net_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("document_url", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_unique_constraint(
        "uq_parliamentary_expense_house_source",
        "parliamentary_expense",
        ["house", "source_key"],
    )
    op.create_index(
        "ix_parliamentary_expense_parl_year",
        "parliamentary_expense",
        ["parliamentarian_id", "year"],
    )
    op.create_index(
        "ix_parliamentary_expense_parliamentarian_id",
        "parliamentary_expense",
        ["parliamentarian_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_parliamentary_expense_parliamentarian_id",
        table_name="parliamentary_expense",
    )
    op.drop_index(
        "ix_parliamentary_expense_parl_year", table_name="parliamentary_expense"
    )
    op.drop_constraint(
        "uq_parliamentary_expense_house_source",
        "parliamentary_expense",
        type_="unique",
    )
    op.drop_table("parliamentary_expense")
