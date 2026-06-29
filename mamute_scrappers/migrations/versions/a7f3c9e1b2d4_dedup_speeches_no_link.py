"""dedup discursos sem speech_link + índice único de guarda

Discursos da Câmara sem urlTexto (ex.: 'PELA ORDEM', 'BREVES COMUNICAÇÕES')
chegavam com speech_link NULL. Como o upsert deduplicava só por speech_link,
cada passada do crawler reinseria o mesmo discurso -> duplicação massiva
(~146k linhas, ~66% da tabela em jun/2026).

Esta migration:
1. Remove as duplicatas existentes mantendo a linha de menor id por chave
   natural (parlamentar + data + hora + tipo + texto). As tabelas-filhas
   (entities/keywords/proposition) têm ON DELETE CASCADE e são limpas junto.
2. Cria um índice único parcial como guarda, impedindo reincidência mesmo que
   a lógica do crawler regrida.

Pré-requisito: o crawler corrigido (dedup por chave natural quando speech_link
é nulo) deve estar deployado junto, para não estourar o índice em novos inserts.

Revision ID: a7f3c9e1b2d4
Revises: e4a9c2b1d7f0
Create Date: 2026-06-30 00:45:00.000000

"""

from __future__ import annotations

from alembic import op


revision = "a7f3c9e1b2d4"
down_revision = "e4a9c2b1d7f0"
branch_labels = None
depends_on = None


_NATURAL_KEY = (
    "parliamentarian_id, date, hour_minute, type, md5(coalesce(speech_text, ''))"
)

_INDEX_NAME = "uq_speeches_transcripts_nolink_natural"


def upgrade() -> None:
    # 1) Deduplicar: manter o menor id por grupo de chave natural.
    op.execute(
        f"""
        DELETE FROM speeches_transcripts s
        USING (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY {_NATURAL_KEY}
                       ORDER BY id
                   ) AS rn
            FROM speeches_transcripts
            WHERE speech_link IS NULL
        ) d
        WHERE s.id = d.id
          AND d.rn > 1
        """
    )

    # 2) Guarda: índice único parcial para linhas sem link.
    op.execute(
        f"""
        CREATE UNIQUE INDEX {_INDEX_NAME}
        ON speeches_transcripts ({_NATURAL_KEY})
        WHERE speech_link IS NULL
        """
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_INDEX_NAME}")
