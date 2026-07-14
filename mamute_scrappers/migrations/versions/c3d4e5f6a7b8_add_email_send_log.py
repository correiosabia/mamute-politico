"""add email_send_log (histórico de envios dos relatórios por e-mail)

Uma linha por tentativa de envio da rotina de notificação (scrappers):
enviado, pulado (sem favoritos / sem atividade) ou erro. A API só lê,
para a aba "E-mails" do painel de métricas.

Revision ID: c3d4e5f6a7b8
Revises: b1c2d3e4f5a6
Create Date: 2026-07-13 12:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "c3d4e5f6a7b8"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_send_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("projeto_id", sa.BigInteger(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("periodicidade", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column(
            "stats",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(
                sa.JSON(), "sqlite"
            ),
            nullable=True,
        ),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_email_send_log_created_at", "email_send_log", ["created_at"]
    )
    op.create_index(
        "ix_email_send_log_projeto_id", "email_send_log", ["projeto_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_email_send_log_projeto_id", table_name="email_send_log")
    op.drop_index("ix_email_send_log_created_at", table_name="email_send_log")
    op.drop_table("email_send_log")
