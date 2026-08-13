"""drop FK de amendment_action_plan.amendment_code

Revision ID: c3d4e5f6a9b0
Revises: b2c3d4e5f6a8
Create Date: 2026-08-13

A FK derrubava a carga inteira. O Transferegov publica plano de acao desde
2020 e a nossa coleta de emendas comeca em 2022: 6.331 dos 57.827 planos
(10,9%, medido) apontam para emenda que nao existe — e nunca vai existir — na
nossa base.

O indice fica: o join continua sendo por igualdade de codigo. O que a FK
acrescentava era so a recusa, e recusar aqui e descartar fato publico por um
vinculo que a fonte nem promete.
"""

from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a9b0"
down_revision = "b2c3d4e5f6a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "amendment_action_plan_amendment_code_fkey",
        "amendment_action_plan",
        type_="foreignkey",
    )


def downgrade() -> None:
    op.create_foreign_key(
        "amendment_action_plan_amendment_code_fkey",
        "amendment_action_plan",
        "parliamentary_amendment",
        ["amendment_code"],
        ["amendment_code"],
        ondelete="SET NULL",
    )
