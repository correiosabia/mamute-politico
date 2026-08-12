"""add feature_flag

Revision ID: a1b2c3d4e5f6
Revises: e6f7a8b9c0d1
Create Date: 2026-08-12

Linha ausente vale `off`, entao feature nova nao exige migration.

A trajetoria e semeada como `admins` porque ja esta visivel para admins em
producao: sem o seed, o deploy a esconderia.
"""

from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feature_flag",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("state", sa.Text(), nullable=False, server_default="off"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state in ('off', 'admins', 'all')", name="ck_feature_flag_state"
        ),
    )
    op.execute(
        "insert into feature_flag (key, state) values ('trajetoria', 'admins')"
    )


def downgrade() -> None:
    op.drop_table("feature_flag")
