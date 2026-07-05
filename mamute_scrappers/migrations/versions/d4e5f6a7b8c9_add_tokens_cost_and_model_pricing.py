"""add token/cost columns to chatbot_usage and model_pricing table

Revision ID: d4e5f6a7b8c9
Revises: c1d2e3f4a5b6
Create Date: 2026-07-05 12:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "d4e5f6a7b8c9"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chatbot_usage", sa.Column("prompt_tokens", sa.Integer(), nullable=True))
    op.add_column("chatbot_usage", sa.Column("completion_tokens", sa.Integer(), nullable=True))
    op.add_column("chatbot_usage", sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True))

    op.create_table(
        "model_pricing",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("input_usd_per_1m", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("output_usd_per_1m", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("currency", sa.Text(), nullable=False, server_default="USD"),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint("model", name="uq_model_pricing_model"),
    )
    op.create_index(op.f("ix_model_pricing_id"), "model_pricing", ["id"], unique=False)

    # Seed aproximado do modelo em uso (source='seed'); o script de sync
    # (scripts/sync_model_pricing.py) sobrescreve com os valores reais do OpenRouter.
    op.execute(
        """
        INSERT INTO model_pricing (model, input_usd_per_1m, output_usd_per_1m, currency, source)
        VALUES ('gemini-2.5-flash', 0.30, 2.50, 'USD', 'seed')
        ON CONFLICT (model) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_model_pricing_id"), table_name="model_pricing")
    op.drop_table("model_pricing")
    op.drop_column("chatbot_usage", "cost_usd")
    op.drop_column("chatbot_usage", "completion_tokens")
    op.drop_column("chatbot_usage", "prompt_tokens")
