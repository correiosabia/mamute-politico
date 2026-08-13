"""ordem pessoal dos parlamentares monitorados (SPEC-001)

Coluna `position` em projetos_parliamentarian: a ordem que o proprio assinante
define para os parlamentares que monitora. NULL significa "nunca ordenado", e a
listagem usa `position NULLS LAST, created_at DESC` — ou seja, enquanto ninguem
ordenou nada o resultado e identico ao comportamento anterior (mais recente
primeiro). Por isso a migracao e puramente aditiva e nao precisa de backfill.

Sem indice unico em (projeto_id, position) de proposito: a reordenacao reescreve
as posicoes 0..n-1 numa transacao so, e um unique conflitaria no meio da
reescrita. A unicidade que importa — um parlamentar por projeto — ja e garantida
por uq_projeto_parliamentarian_unique.

Revision ID: 4eecac3244dc
Revises: b2c3d4e5f6a8
Create Date: 2026-08-11 10:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4eecac3244dc"
down_revision: Union[str, None] = "b2c3d4e5f6a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projetos_parliamentarian",
        sa.Column("position", sa.Integer(), nullable=True),
    )
    # A leitura sempre filtra por projeto antes de ordenar, entao o indice util
    # e o composto — nao um indice so em position.
    op.create_index(
        "ix_projetos_parliamentarian_projeto_position",
        "projetos_parliamentarian",
        ["projeto_id", "position"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_projetos_parliamentarian_projeto_position",
        table_name="projetos_parliamentarian",
    )
    op.drop_column("projetos_parliamentarian", "position")
