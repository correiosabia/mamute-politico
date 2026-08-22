"""seed qtd_candidatos nos planos e libera notificacoes em todos

CS-62. Duas coisas que o mecanismo de flags/tiers nao faz sozinho:

1. `qtd_candidatos` — quantas candidaturas da eleicao o plano pode monitorar.
   Default 10, decidido com o time. Sem o seed, plano existente ficaria sem a
   chave e o painel mostraria campo vazio. Plano NOVO vindo do sync do Ghost
   herda a chave do plano-fonte (ENTITLEMENT_KEYS em ghost_tiers_sync.py).

2. `notificacoes` — a flag do sino tem de nascer liberada em TODO plano quando
   o admin ligar o tri-estado, e nao oculta (que e o default de
   `feature_flag_tier`). Mesmo padrao do seed de 'emendas' na b8f4d2a91c57: a
   linha 'liberado' entra agora; o tri-estado segue em `off` e continua sendo o
   interruptor. Nao seedamos `feature_flag` aqui de proposito — quem liga a
   feature e o admin, nao a migration.

`busca_candidaturas` NAO recebe seed: por decisao de produto, plano sem o
recurso vai de **cadeado** (vitrine para instigar a assinatura), o que e
configurado plano a plano na tela de Planos.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-08-22 10:00:00.000000

"""

from __future__ import annotations

from alembic import op


revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None

QTD_CANDIDATOS_DEFAULT = 10


def upgrade() -> None:
    # jsonb_set com create_if_missing=true: nao sobrescreve plano que ja tenha
    # um valor combinado a mao.
    op.execute(
        "UPDATE tiers "
        "SET detalhes = jsonb_set("
        "  coalesce(detalhes, '{}'::jsonb), '{qtd_candidatos}', "
        f"  '{QTD_CANDIDATOS_DEFAULT}'::jsonb, true) "
        "WHERE detalhes -> 'qtd_candidatos' IS NULL"
    )
    op.execute(
        "insert into feature_flag_tier (flag_key, tier_id, mode) "
        "select 'notificacoes', id, 'liberado' from tiers "
        "where deleted_at is null "
        "on conflict do nothing"
    )


def downgrade() -> None:
    op.execute("delete from feature_flag_tier where flag_key = 'notificacoes'")
    op.execute("UPDATE tiers SET detalhes = detalhes - 'qtd_candidatos'")
