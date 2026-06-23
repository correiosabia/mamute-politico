"""add chatbot usage table

Revision ID: e4a9c2b1d7f0
Revises: 7c91a3e2f4d8
Create Date: 2026-06-23 12:35:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e4a9c2b1d7f0"
down_revision = "7c91a3e2f4d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chatbot_usage",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("projeto_id", sa.BigInteger(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("question_chars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("answer_chars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["projeto_id"],
            ["projetos.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("request_id", name="uq_chatbot_usage_request_id"),
    )
    op.create_index(op.f("ix_chatbot_usage_id"), "chatbot_usage", ["id"], unique=False)
    op.create_index("ix_chatbot_usage_projeto_period", "chatbot_usage", ["projeto_id", "period_start"])
    op.create_index("ix_chatbot_usage_email_period", "chatbot_usage", ["email", "period_start"])
    op.create_index("ix_chatbot_usage_status", "chatbot_usage", ["status"])


def downgrade() -> None:
    op.drop_index("ix_chatbot_usage_status", table_name="chatbot_usage")
    op.drop_index("ix_chatbot_usage_email_period", table_name="chatbot_usage")
    op.drop_index("ix_chatbot_usage_projeto_period", table_name="chatbot_usage")
    op.drop_index(op.f("ix_chatbot_usage_id"), table_name="chatbot_usage")
    op.drop_table("chatbot_usage")
