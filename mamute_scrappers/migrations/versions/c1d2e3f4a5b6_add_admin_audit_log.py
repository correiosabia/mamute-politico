"""add admin audit log table

Revision ID: c1d2e3f4a5b6
Revises: a7f3c9e1b2d4
Create Date: 2026-07-04 12:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "c1d2e3f4a5b6"
down_revision = "a7f3c9e1b2d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("admin_email", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=True),
        sa.Column("before", sa.Text(), nullable=True),
        sa.Column("after", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(op.f("ix_admin_audit_log_id"), "admin_audit_log", ["id"], unique=False)
    op.create_index(
        "ix_admin_audit_log_entity", "admin_audit_log", ["entity", "entity_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_admin_audit_log_entity", table_name="admin_audit_log")
    op.drop_index(op.f("ix_admin_audit_log_id"), table_name="admin_audit_log")
    op.drop_table("admin_audit_log")
