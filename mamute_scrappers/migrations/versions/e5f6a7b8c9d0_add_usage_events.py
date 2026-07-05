"""add usage_events table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-05 14:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usage_events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("projeto_id", sa.BigInteger(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("page", sa.Text(), nullable=True),
        sa.Column("parliamentarian_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(op.f("ix_usage_events_id"), "usage_events", ["id"], unique=False)
    op.create_index("ix_usage_events_projeto_type", "usage_events", ["projeto_id", "event_type"])
    op.create_index("ix_usage_events_created_at", "usage_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_usage_events_created_at", table_name="usage_events")
    op.drop_index("ix_usage_events_projeto_type", table_name="usage_events")
    op.drop_index(op.f("ix_usage_events_id"), table_name="usage_events")
    op.drop_table("usage_events")
