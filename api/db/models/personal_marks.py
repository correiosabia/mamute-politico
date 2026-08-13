"""Marcacoes pessoais que o assinante faz sobre politicos — SPEC-001.

Sao camadas sobre o vinculo de monitoramento (`projetos_parliamentarian`), nao
um segundo "favorito": monitorar continua sendo a unica relacao medida pela
cota do plano. Aqui ficam as tags livres; a marcacao de voto vive em tabela
propria, com regime de privacidade diferente, e entra numa fatia posterior.

`projeto_id` aparece denormalizado em `parliamentarian_tag` DE PROPOSITO: com
ele, toda checagem de escopo vira um `WHERE projeto_id = :id` direto, sem
depender de quem escreve a query lembrar do join com `project_tag`. Esse
esquecimento e exatamente a falha que a clausula 0e existe para evitar.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..base import Base


class ProjectTag(Base):
    """Tag livre criada pelo assinante (ex.: "transparencia", "meio ambiente")."""

    __tablename__ = "project_tag"
    __table_args__ = (
        # "Meio Ambiente" e "meio ambiente" sao a mesma tag: a unicidade e pelo
        # slug normalizado, e `name` guarda a forma que a pessoa digitou.
        UniqueConstraint("projeto_id", "slug", name="uq_project_tag_projeto_slug"),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    projeto_id = Column(
        BigInteger,
        ForeignKey("projetos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(Text, nullable=False)
    slug = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    projeto = relationship("Projetos")
    parlamentares = relationship(
        "ParliamentarianTag",
        back_populates="tag",
        cascade="all, delete-orphan",
    )


class ParliamentarianTag(Base):
    """Aplicacao de uma tag do projeto a um parlamentar."""

    __tablename__ = "parliamentarian_tag"
    __table_args__ = (
        UniqueConstraint(
            "tag_id",
            "parliamentarian_id",
            name="uq_parliamentarian_tag_unique",
        ),
        Index("ix_parliamentarian_tag_projeto_parlamentar", "projeto_id", "parliamentarian_id"),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    projeto_id = Column(
        BigInteger,
        ForeignKey("projetos.id", ondelete="CASCADE"),
        nullable=False,
    )
    tag_id = Column(
        BigInteger,
        ForeignKey("project_tag.id", ondelete="CASCADE"),
        nullable=False,
    )
    parliamentarian_id = Column(
        BigInteger,
        ForeignKey("parliamentarian.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    tag = relationship("ProjectTag", back_populates="parlamentares")


class ProjectMamutometro(Base):
    """Marcacao do mamutometro: um nivel de 1..N que o assinante da a um politico.

    O SIGNIFICADO DE CADA NIVEL NAO EXISTE AQUI, e isso e o desenho, nao uma
    omissao. Cada assinante escolhe a propria regra ("3 = votei", "3 = acompanho
    de perto", "1 = desconfio") e nunca a informa ao sistema. Por isso o campo se
    chama `level` e nada mais: nome de coluna e documentacao, e batizar de
    `afinidade` ou `apoio` fixaria no schema justamente a semantica que o produto
    se compromete a nao ter.

    E por isso tambem que nao ha cifra aqui, ao contrario do desenho anterior
    (marcacao de voto declarada): o banco nao consegue responder "quem votou no
    politico X" porque nivel 3 nao e voto. O que protege continua sendo escopo
    por token, zero visibilidade no admin, zero agregado por politico e remocao
    de verdade. Detalhes em .sdd/specs/001-.../plano.md.

    `level` nao tem CHECK contra o tamanho da regua: a regua e configuracao
    mutavel (`marcacoes_config`), e amarrar o schema a ela transformaria mudanca
    de configuracao em perda de dado do assinante.
    """

    __tablename__ = "project_mamutometro"
    __table_args__ = (
        UniqueConstraint(
            "projeto_id",
            "parliamentarian_id",
            name="uq_project_mamutometro_unique",
        ),
        CheckConstraint("level >= 1", name="ck_project_mamutometro_level_positivo"),
        Index("ix_project_mamutometro_projeto", "projeto_id"),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    projeto_id = Column(
        BigInteger,
        ForeignKey("projetos.id", ondelete="CASCADE"),
        nullable=False,
    )
    parliamentarian_id = Column(
        BigInteger,
        ForeignKey("parliamentarian.id", ondelete="CASCADE"),
        nullable=False,
    )
    level = Column(SmallInteger, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


__all__ = ["ProjectTag", "ParliamentarianTag", "ProjectMamutometro"]
