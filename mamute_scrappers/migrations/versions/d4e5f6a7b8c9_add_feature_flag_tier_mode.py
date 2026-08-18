"""add feature_flag_tier mode

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a9b0
Create Date: 2026-08-18

CS-58: o vinculo plano x feature deixa de ser binario (linha presente =
liberado) e ganha modo: 'liberado' (acesso pleno) ou 'cadeado' (entrada
visivel + previa desfocada). Ausencia de linha segue valendo oculto.

Seed de 'emendas': a aba EMENDAS hoje e aberta a todos; sem o seed, criar a
flag a esconderia no deploy. 'all' + linha 'liberado' em todo tier ativo
preserva o comportamento atual ate o admin configurar o cadeado.
"""

from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "feature_flag_tier",
        sa.Column("mode", sa.Text(), nullable=False, server_default="liberado"),
    )
    op.create_check_constraint(
        "ck_feature_flag_tier_mode",
        "feature_flag_tier",
        "mode in ('liberado', 'cadeado')",
    )
    op.execute(
        "insert into feature_flag (key, state) values ('emendas', 'all') "
        "on conflict (key) do nothing"
    )
    op.execute(
        "insert into feature_flag_tier (flag_key, tier_id, mode) "
        "select 'emendas', id, 'liberado' from tiers where deleted_at is null "
        "on conflict do nothing"
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_feature_flag_tier_mode", "feature_flag_tier", type_="check"
    )
    op.drop_column("feature_flag_tier", "mode")
    op.execute("delete from feature_flag_tier where flag_key = 'emendas'")
    op.execute("delete from feature_flag where key = 'emendas'")
