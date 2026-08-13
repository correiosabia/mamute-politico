"""Configuracao das marcacoes pessoais (SPEC-001), editavel pelo painel admin.

Uma tabela para a spec inteira, e nao uma por feature: e um bloco so na tela de
configuracoes, e evita a proliferacao de tabelas de linha unica.

O QUE NAO ESTA AQUI, de proposito:

* **quais planos tem mamutometro** — vive em `feature_flag_tier`, o recorte por
  plano que a PR #169 criou. De fabrica, so os planos pagos.
* **quantos politicos cada plano pode marcar** — vive em `tiers.detalhes`
  (`qtd_mamutometro`), ao lado de `qtd_termos` e `qtd_consultas_ia_mes`, com a
  precedencia por `MAMUTE_TIER_LIMITS_JSON` que o README ja documenta.

Ou seja: o que e decisao comercial fica onde as decisoes comerciais moram, e o
que e decisao de produto fica aqui. `mamutometro_max_level` e o tamanho da
regua, e e global de proposito — se variasse por plano, a mesma marcacao
significaria coisas diferentes conforme quem olha.

REGRA QUE ATRAVESSA TUDO: mudar configuracao NUNCA apaga marcacao de assinante.
Baixar a regua, apertar o escopo ou tirar a feature de um plano deixa as linhas
onde estao; o dado fica dormente e volta se a configuracao voltar.
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    SmallInteger,
    Text,
)
from sqlalchemy.sql import func

from ..base import Base

ESCOPO_MONITORADOS = "monitorados"
ESCOPO_TODOS = "todos"
ESCOPOS_VALIDOS = (ESCOPO_MONITORADOS, ESCOPO_TODOS)

LINHA_UNICA_ID = 1
MAX_LEVEL_PADRAO = 3
MAX_LEVEL_MINIMO = 1
MAX_LEVEL_MAXIMO = 5

# Texto de fabrica do aviso de primeira utilizacao. E deliberadamente NEUTRO:
# nao sugere o que cada nivel significa, porque sugerir seria reintroduzir a
# semantica que o desenho inteiro remove. Editavel pelo painel — e a revisao
# desse texto e o ponto onde a neutralidade mais escorrega.
NOTICE_PADRAO = (
    "O mamutômetro é seu. Você decide o que cada nível significa — o Mamute não "
    "sabe e não pergunta. Ninguém além de você enxerga suas marcações, e você "
    "pode apagar todas quando quiser."
)


class MarcacoesConfig(Base):
    """Linha unica de configuracao das marcacoes pessoais."""

    __tablename__ = "marcacoes_config"
    __table_args__ = (
        # Linha unica garantida pelo banco, nao por convencao: configuracao
        # global com duas linhas e bug silencioso, do tipo que so aparece
        # quando dois ambientes discordam.
        CheckConstraint("id = 1", name="ck_marcacoes_config_linha_unica"),
        CheckConstraint(
            f"mamutometro_max_level BETWEEN {MAX_LEVEL_MINIMO} AND {MAX_LEVEL_MAXIMO}",
            name="ck_marcacoes_config_max_level",
        ),
        CheckConstraint(
            "mamutometro_escopo IN ('monitorados', 'todos')",
            name="ck_marcacoes_config_mamutometro_escopo",
        ),
        CheckConstraint(
            "tags_escopo IN ('monitorados', 'todos')",
            name="ck_marcacoes_config_tags_escopo",
        ),
    )

    id = Column(SmallInteger, primary_key=True, default=LINHA_UNICA_ID)
    # Tamanho da regua: de quantos mamutes a escala e feita (1..5).
    mamutometro_max_level = Column(
        SmallInteger, nullable=False, server_default=str(MAX_LEVEL_PADRAO)
    )
    mamutometro_notice_text = Column(Text, nullable=False)
    # Quem pode receber marcacao: so quem o assinante monitora, ou qualquer um
    # visivel no catalogo. Nasce em "monitorados" (pedido do PO).
    mamutometro_escopo = Column(
        Text, nullable=False, server_default=ESCOPO_MONITORADOS
    )
    # Tags nascem em "todos", que e o comportamento ja entregue — a config
    # existe para poder apertar, nao para mudar o padrao.
    tags_escopo = Column(Text, nullable=False, server_default=ESCOPO_TODOS)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


__all__ = [
    "MarcacoesConfig",
    "ESCOPO_MONITORADOS",
    "ESCOPO_TODOS",
    "ESCOPOS_VALIDOS",
    "LINHA_UNICA_ID",
    "MAX_LEVEL_PADRAO",
    "MAX_LEVEL_MINIMO",
    "MAX_LEVEL_MAXIMO",
    "NOTICE_PADRAO",
]
