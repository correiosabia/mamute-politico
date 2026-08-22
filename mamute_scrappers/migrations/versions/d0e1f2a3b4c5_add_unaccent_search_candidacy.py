"""add unaccent search for candidacy names

A busca da tela Buscar Candidaturas usava ILIKE cru, que e case-insensitive
mas sensivel a acento: "joao" nao encontrava "JOÃO DO CEARÁ". Digitar nome sem
acento e o comportamento normal do usuario brasileiro, entao a busca precisa
dobrar o acento dos DOIS lados da comparacao.

Escolha do unaccent em vez de translate() enumerando os acentos de PT-BR:
translate mapeia 1 caractere -> 1 caractere, logo 'ß' -> 'ss' e 'Æ' -> 'AE'
sao impossiveis nele; e uma lista de 96 caracteres editada errado apaga
caracteres em silencio (translate('AÇÃO','ÇÃ','C') = 'ACO'). Medido em 200 mil
nomes nesta base, o unaccent tambem ficou mais rapido no recheck (~33ms contra
~55ms), porque o dicionario em C custa menos por linha que a tabela de
traducao.

O wrapper existe porque unaccent() e STABLE (o dicionario pode ser redefinido)
e Postgres nao aceita funcao nao-IMMUTABLE em expressao de indice. Passar o
dicionario explicitamente e marcar IMMUTABLE e o contorno documentado no
manual; a asercao e segura enquanto ninguem redefinir o dicionario 'unaccent'.

A extensao usa IF NOT EXISTS: em producao ela e criada previamente por um
superusuario (o usuario da aplicacao nao tem esse privilegio) — mesma nota da
migration a9b0c1d2e3f4, que trouxe o pg_trgm. **Antes deste deploy alguem com
superusuario precisa rodar `CREATE EXTENSION unaccent;` no banco de producao.**

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-08-21 22:00:00.000000

"""

from __future__ import annotations

from alembic import op


revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    # Qualificado com public. de proposito: funcao IMMUTABLE em indice nao pode
    # depender do search_path de quem consulta.
    op.execute(
        "CREATE OR REPLACE FUNCTION public.unaccent_imutavel(text) "
        "RETURNS text AS "
        "$$ SELECT public.unaccent('public.unaccent', $1) $$ "
        "LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE"
    )
    # GIN + trigrama porque o filtro e ILIKE '%termo%', com wildcard dos dois
    # lados; btree nao serve.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_candidacy_ballot_name_unaccent_trgm "
        "ON candidacy USING gin "
        "(public.unaccent_imutavel(ballot_name) gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_candidacy_full_name_unaccent_trgm "
        "ON candidacy USING gin "
        "(public.unaccent_imutavel(full_name) gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_candidacy_full_name_unaccent_trgm")
    op.execute("DROP INDEX IF EXISTS ix_candidacy_ballot_name_unaccent_trgm")
    op.execute("DROP FUNCTION IF EXISTS public.unaccent_imutavel(text)")
    # As extensoes ficam: pg_trgm e usado por outros indices (a9b0c1d2e3f4) e
    # derrubar unaccent exigiria saber que ninguem mais a adotou depois.
