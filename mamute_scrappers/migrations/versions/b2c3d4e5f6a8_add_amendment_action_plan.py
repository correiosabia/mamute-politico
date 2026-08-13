"""add amendment_action_plan

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f6
Create Date: 2026-08-12

Planos de acao das emendas Pix, vindos do Transferegov. ~58 mil linhas na
primeira carga. A prestacao de contas fica desnormalizada na mesma tabela: a
fonte tem 1,02 relatorio por plano, entao guardar o mais forte basta.
"""

from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a8"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "amendment_action_plan",
        sa.Column("id_plano_acao", sa.BigInteger(), primary_key=True),
        sa.Column("codigo_plano_acao", sa.Text()),
        sa.Column("amendment_code", sa.Text(), nullable=True),
        sa.Column("ano", sa.Integer()),
        sa.Column("situacao", sa.Text()),
        sa.Column("beneficiario_nome", sa.Text()),
        sa.Column("beneficiario_cnpj", sa.Text()),
        sa.Column("beneficiario_uf", sa.Text()),
        sa.Column("valor_custeio", sa.Numeric(18, 2)),
        sa.Column("valor_investimento", sa.Numeric(18, 2)),
        sa.Column("prestacao_situacao", sa.Text()),
        sa.Column("prestacao_tipo", sa.Text()),
        sa.Column("prestacao_valor_executado", sa.Numeric(18, 2)),
        sa.Column("prestacao_valor_pendente", sa.Numeric(18, 2)),
        sa.Column("prestacao_data", sa.Text()),
        sa.Column("prestacao_origem", sa.Text()),
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
        # SET NULL: o plano de acao e fato publico e nao deve sumir se a emenda
        # sair da base. Mesma politica de parliamentary_amendment.
        sa.ForeignKeyConstraint(
            ["amendment_code"],
            ["parliamentary_amendment.amendment_code"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_amendment_action_plan_amendment_code",
        "amendment_action_plan",
        ["amendment_code"],
    )
    op.create_index(
        "ix_amendment_action_plan_ano", "amendment_action_plan", ["ano"]
    )


def downgrade() -> None:
    op.drop_table("amendment_action_plan")
