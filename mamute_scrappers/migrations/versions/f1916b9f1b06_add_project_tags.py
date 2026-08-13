"""tags livres do assinante sobre politicos (SPEC-001)

Duas tabelas: `project_tag` (a tag em si, unica por projeto pelo slug
normalizado) e `parliamentarian_tag` (a aplicacao da tag a um parlamentar).

`parliamentarian_tag.projeto_id` e denormalizado de proposito: com ele toda
checagem de escopo vira um WHERE direto, sem depender de quem escreve a query
lembrar do join com project_tag — que e a falha que a clausula 0e evita.

Nenhuma tabela existente muda. Tags nao consomem cota de plano: o que o plano
mede e monitoramento, nao organizacao pessoal.

Revision ID: f1916b9f1b06
Revises: 4eecac3244dc
Create Date: 2026-08-13 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f1916b9f1b06"
down_revision: Union[str, None] = "4eecac3244dc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_tag",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "projeto_id",
            sa.BigInteger(),
            sa.ForeignKey("projetos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("projeto_id", "slug", name="uq_project_tag_projeto_slug"),
    )
    op.create_index("ix_project_tag_projeto_id", "project_tag", ["projeto_id"])

    op.create_table(
        "parliamentarian_tag",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "projeto_id",
            sa.BigInteger(),
            sa.ForeignKey("projetos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tag_id",
            sa.BigInteger(),
            sa.ForeignKey("project_tag.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parliamentarian_id",
            sa.BigInteger(),
            sa.ForeignKey("parliamentarian.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "tag_id", "parliamentarian_id", name="uq_parliamentarian_tag_unique"
        ),
    )
    op.create_index(
        "ix_parliamentarian_tag_projeto_parlamentar",
        "parliamentarian_tag",
        ["projeto_id", "parliamentarian_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_parliamentarian_tag_projeto_parlamentar", table_name="parliamentarian_tag"
    )
    op.drop_table("parliamentarian_tag")
    op.drop_index("ix_project_tag_projeto_id", table_name="project_tag")
    op.drop_table("project_tag")
