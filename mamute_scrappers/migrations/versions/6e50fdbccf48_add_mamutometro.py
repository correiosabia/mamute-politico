"""mamutometro e configuracao das marcacoes pessoais (SPEC-001)

`project_mamutometro` guarda um nivel de 1..N que o assinante da a um politico.
O SIGNIFICADO de cada nivel nao existe no banco: cada pessoa escolhe a propria
regra e nunca a informa. Por isso a coluna se chama `level` e nada mais, e por
isso nao ha cifra — o banco nao responde "quem votou no politico X" porque
nivel 3 nao e voto.

`marcacoes_config` e a linha unica de configuracao da spec inteira: tamanho da
regua (global), texto do aviso e os dois escopos. Nasce preenchida, para a
feature nunca subir sem configuracao.

Padrao de fabrica pedido pelo PO — mamutometro so em plano PAGO — e aplicado
liberando a flag `mamutometro` para os tiers pagos existentes em
`feature_flag_tier`. Plano novo (vindo do sync do Ghost) nasce sem a feature,
que e o comportamento ja documentado daquela tabela.

Revision ID: 6e50fdbccf48
Revises: f1916b9f1b06
Create Date: 2026-08-13 12:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6e50fdbccf48"
down_revision: Union[str, None] = "f1916b9f1b06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOTICE_PADRAO = (
    "O mamutômetro é seu. Você decide o que cada nível significa — o Mamute não "
    "sabe e não pergunta. Ninguém além de você enxerga suas marcações, e você "
    "pode apagar todas quando quiser."
)


def upgrade() -> None:
    op.create_table(
        "project_mamutometro",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "projeto_id",
            sa.BigInteger(),
            sa.ForeignKey("projetos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parliamentarian_id",
            sa.BigInteger(),
            sa.ForeignKey("parliamentarian.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("level", sa.SmallInteger(), nullable=False),
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
        sa.UniqueConstraint(
            "projeto_id", "parliamentarian_id", name="uq_project_mamutometro_unique"
        ),
        # Sem CHECK contra o tamanho da regua: a regua e configuracao mutavel, e
        # amarrar o schema a ela transformaria mudanca de config em perda de dado.
        sa.CheckConstraint("level >= 1", name="ck_project_mamutometro_level_positivo"),
    )
    op.create_index(
        "ix_project_mamutometro_projeto", "project_mamutometro", ["projeto_id"]
    )

    op.create_table(
        "marcacoes_config",
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column(
            "mamutometro_max_level",
            sa.SmallInteger(),
            nullable=False,
            server_default="3",
        ),
        sa.Column("mamutometro_notice_text", sa.Text(), nullable=False),
        sa.Column(
            "mamutometro_escopo",
            sa.Text(),
            nullable=False,
            server_default="monitorados",
        ),
        sa.Column("tags_escopo", sa.Text(), nullable=False, server_default="todos"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="ck_marcacoes_config_linha_unica"),
        sa.CheckConstraint(
            "mamutometro_max_level BETWEEN 1 AND 5",
            name="ck_marcacoes_config_max_level",
        ),
        sa.CheckConstraint(
            "mamutometro_escopo IN ('monitorados', 'todos')",
            name="ck_marcacoes_config_mamutometro_escopo",
        ),
        sa.CheckConstraint(
            "tags_escopo IN ('monitorados', 'todos')",
            name="ck_marcacoes_config_tags_escopo",
        ),
    )

    # Config nasce preenchida: a feature nunca sobe sem configuracao valida.
    op.execute(
        sa.text(
            """
            INSERT INTO marcacoes_config
                (id, mamutometro_max_level, mamutometro_notice_text,
                 mamutometro_escopo, tags_escopo)
            VALUES (1, 3, :notice, 'monitorados', 'todos')
            """
        ).bindparams(notice=NOTICE_PADRAO)
    )

    # De fabrica: mamutometro so nos planos pagos. "free" e o identificador do
    # plano gratuito (ver README, secao de tiers). Planos criados depois nascem
    # sem a feature, como manda o desenho de feature_flag_tier.
    op.execute(
        """
        INSERT INTO feature_flag_tier (flag_key, tier_id)
        SELECT 'mamutometro', id FROM tiers
        WHERE deleted_at IS NULL AND product_id <> 'free'
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM feature_flag_tier WHERE flag_key = 'mamutometro'")
    op.drop_table("marcacoes_config")
    op.drop_index("ix_project_mamutometro_projeto", table_name="project_mamutometro")
    op.drop_table("project_mamutometro")
