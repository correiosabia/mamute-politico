"""add trigram indexes for speeches ILIKE search

O SQL context do chatbot filtra speeches_transcripts com ILIKE '%kw%' em
speech_text/summary. Sem índice isso é seq scan de 120k+ discursos longos
(~15s frio por consulta, e são 5 consultas por pergunta do chat). GIN +
pg_trgm atende ILIKE com wildcard dos dois lados.

A extensão usa IF NOT EXISTS: em produção ela é criada previamente por um
superusuário (o usuário da aplicação não tem esse privilégio); no smoke de
CI o usuário do serviço Postgres é superuser e cria na hora.

Revision ID: a9b0c1d2e3f4
Revises: d5e6f7a8b9c0
Create Date: 2026-08-02 12:00:00.000000

"""

from __future__ import annotations

from alembic import op


revision = "a9b0c1d2e3f4"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_speeches_transcripts_speech_text_trgm "
        "ON speeches_transcripts USING gin (speech_text gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_speeches_transcripts_summary_trgm "
        "ON speeches_transcripts USING gin (summary gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_speeches_transcripts_summary_trgm")
    op.execute("DROP INDEX IF EXISTS ix_speeches_transcripts_speech_text_trgm")
    # A extensão fica: pode estar em uso por outros índices/consultas.
