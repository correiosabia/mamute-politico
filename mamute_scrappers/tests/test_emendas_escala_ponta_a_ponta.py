"""Camadas 1 e 3 contra o bug de escala, do laco de coleta ate o banco.

Cenario reproduzido: a listagem paginada devolve `10,00` para uma emenda de
`100.000,00` (medido na fonte em 2026-08-12, emenda 202644380004), e a consulta
por codigo devolve o valor certo.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Iterator, List, Optional

import pytest
from sqlalchemy import Column, ForeignKey, Integer, Numeric, Text, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from mamute_scrappers.portal_crawler import client as client_mod
from mamute_scrappers.portal_crawler import emendas as emendas_mod

Base = declarative_base()


class Parliamentarian(Base):
    __tablename__ = "parliamentarian"
    id = Column(Integer, primary_key=True)
    name = Column(Text)
    full_name = Column(Text)


class ParliamentaryAmendment(Base):
    __tablename__ = "parliamentary_amendment"
    id = Column(Integer, primary_key=True)
    amendment_code = Column(Text, nullable=False, unique=True)
    year = Column(Integer)
    amendment_number = Column(Text)
    amendment_type = Column(Text)
    author_name_raw = Column(Text)
    author_raw = Column(Text)
    parliamentarian_id = Column(Integer, ForeignKey("parliamentarian.id"))
    match_status = Column(Text, nullable=False)
    spending_locality = Column(Text)
    function = Column(Text)
    subfunction = Column(Text)
    committed_value = Column(Numeric(18, 2))
    settled_value = Column(Numeric(18, 2))
    paid_value = Column(Numeric(18, 2))
    remainder_inscribed = Column(Numeric(18, 2))
    remainder_cancelled = Column(Numeric(18, 2))
    remainder_paid = Column(Numeric(18, 2))


@pytest.fixture()
def limpar_travas() -> Iterator[None]:
    emendas_mod._travas.clear()
    yield
    emendas_mod._travas.clear()


@pytest.fixture()
def session(monkeypatch) -> Iterator[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(emendas_mod, "ParliamentaryAmendment", ParliamentaryAmendment)
    emendas_mod._travas.clear()
    with maker() as s:
        yield s


def item(codigo: str, empenhado: str, liquidado: str, pago: str) -> Dict[str, Any]:
    return {
        "codigoEmenda": codigo,
        "ano": 2026,
        "tipoEmenda": "Emenda Individual - Transferências com Finalidade Definida",
        "autor": "NETO CARLETTO",
        "nomeAutor": "NETO CARLETTO",
        "numeroEmenda": codigo[-4:],
        "localidadeDoGasto": "EUNÁPOLIS - BA",
        "funcao": "Assistência social",
        "subfuncao": "SERVICOS SOCIOASSISTENCIAIS",
        "valorEmpenhado": empenhado,
        "valorLiquidado": liquidado,
        "valorPago": pago,
        "valorRestoInscrito": "0,00",
        "valorRestoCancelado": "0,00",
        "valorRestoPago": "0,00",
    }


class ClienteFalso:
    """Cliente que devolve paginas fixas e conta as releituras por codigo."""

    def __init__(
        self,
        paginas: List[List[Dict[str, Any]]],
        por_codigo: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._paginas = paginas
        self._por_codigo = por_codigo or {}
        self.releituras: List[str] = []

    def iter_amendments(self, year: int) -> Iterator[Dict[str, Any]]:
        for pagina in self._paginas:
            yield from pagina

    def fetch_amendment(self, amendment_code: str) -> Optional[Dict[str, Any]]:
        self.releituras.append(amendment_code)
        resposta = self._por_codigo.get(amendment_code)
        if isinstance(resposta, list):
            # Sequencia de respostas, uma por tentativa.
            indice = self.releituras.count(amendment_code) - 1
            return resposta[min(indice, len(resposta) - 1)]
        return resposta


def varrer(cliente: ClienteFalso) -> List[Dict[str, Any]]:
    """Roda os itens pelo mesmo caminho do laco de coleta, sem banco.

    Espelha `emendas()`: um unico `maior_empenhado` atravessa a varredura
    inteira, que e o que faz o detector de ordem funcionar.
    """
    maior = None
    preparados = []
    for item_bruto in cliente.iter_amendments(2026):
        payload = emendas_mod.build_payload(item_bruto)
        payload, maior = emendas_mod.conferir_escala(cliente, payload, maior)
        preparados.append(payload)
    return preparados


# --- camada 1: trava de escrita ----------------------------------------------


def base_payload(**overrides) -> Dict[str, Any]:
    payload = emendas_mod.build_payload(
        item("202644380004", "100.000,00", "100.000,00", "100.000,00")
    )
    payload.update({"parliamentarian_id": None, "match_status": "unmatched"})
    payload.update(overrides)
    return payload


def test_valor_dividido_nao_sobrescreve_valor_bom_gravado(session):
    emendas_mod.upsert_amendment(session, base_payload())
    session.commit()

    emendas_mod.upsert_amendment(
        session,
        base_payload(
            committed_value=Decimal("10.00"),
            settled_value=Decimal("10.00"),
            paid_value=Decimal("10.00"),
        ),
    )
    session.commit()

    registro = session.query(ParliamentaryAmendment).one()
    assert registro.committed_value == Decimal("100000.00")
    assert registro.settled_value == Decimal("100000.00")
    assert registro.paid_value == Decimal("100000.00")
    assert emendas_mod._travas["escrita_recusada"] == 3


def test_valor_correto_conserta_linha_ja_corrompida(session):
    """Crescimento continua sendo aceito — e o que faz a linha errada se curar
    sozinha no primeiro run que ler certo."""
    emendas_mod.upsert_amendment(
        session,
        base_payload(
            committed_value=Decimal("10.00"),
            settled_value=Decimal("10.00"),
            paid_value=Decimal("10.00"),
        ),
    )
    session.commit()

    emendas_mod.upsert_amendment(session, base_payload())
    session.commit()

    registro = session.query(ParliamentaryAmendment).one()
    assert registro.committed_value == Decimal("100000.00")


def test_queda_legitima_de_valor_continua_passando(session):
    """A trava e estreita de proposito: so recusa a razao exata de 10.000."""
    emendas_mod.upsert_amendment(session, base_payload())
    session.commit()

    emendas_mod.upsert_amendment(
        session, base_payload(committed_value=Decimal("0.00"))
    )
    session.commit()

    registro = session.query(ParliamentaryAmendment).one()
    assert registro.committed_value == Decimal("0.00")


def test_campo_sem_desempate_preserva_o_gravado_e_nao_apaga(session):
    emendas_mod.upsert_amendment(session, base_payload())
    session.commit()

    emendas_mod.upsert_amendment(
        session,
        base_payload(
            committed_value=Decimal("10.00"),
            _nao_confirmados=frozenset({"committed_value"}),
        ),
    )
    session.commit()

    assert (
        session.query(ParliamentaryAmendment).one().committed_value
        == Decimal("100000.00")
    )


def test_linha_nova_sem_desempate_fica_nula_em_vez_de_publicar_valor_suspeito(session):
    emendas_mod.upsert_amendment(
        session,
        base_payload(
            committed_value=Decimal("10.00"),
            _nao_confirmados=frozenset({"committed_value"}),
        ),
    )
    session.commit()

    registro = session.query(ParliamentaryAmendment).one()
    assert registro.committed_value is None
    # Os campos que nao estavam sob suspeita seguem gravados.
    assert registro.paid_value == Decimal("100000.00")


# --- camada 3: desempate por releitura ---------------------------------------


def test_valor_fora_de_ordem_dispara_releitura_e_corrige(limpar_travas):
    cliente = ClienteFalso(
        [
            [
                item("202600000001", "99.999,96", "0,00", "0,00"),
                item("202644380004", "10,00", "10,00", "10,00"),
            ]
        ],
        {
            "202644380004": item(
                "202644380004", "100.000,00", "100.000,00", "100.000,00"
            )
        },
    )

    preparados = varrer(cliente)

    assert cliente.releituras == ["202644380004"]
    suspeita = preparados[-1]
    assert suspeita["committed_value"] == Decimal("100000.00")
    assert suspeita["settled_value"] == Decimal("100000.00")
    assert suspeita["paid_value"] == Decimal("100000.00")
    assert "_nao_confirmados" not in suspeita
    assert emendas_mod._travas["desempatado"] == 1


def test_sequencia_crescente_nao_gasta_nenhuma_releitura(limpar_travas):
    """Valores reais da pagina 1 de 2026, na ordem em que a fonte devolve."""
    cliente = ClienteFalso(
        [
            [
                item("202600000001", "7,00", "7,00", "0,00"),
                item("202600000002", "239,03", "239,03", "239,03"),
                item("202600000003", "100.000,00", "0,00", "0,00"),
                item("202600000004", "1.393.000,00", "638.087,12", "0,00"),
            ]
        ]
    )

    varrer(cliente)

    assert cliente.releituras == []
    assert emendas_mod._travas["suspeitos"] == 0


def test_releitura_tambem_dividida_nao_publica_valor_inferido(limpar_travas):
    """A consulta por codigo tambem erra (1 em 30 medido). Quando as duas
    leituras vem divididas, nao gravamos `10,00 x 10.000` por inferencia — o
    campo vai marcado para o upsert preservar o que ja estava."""
    cliente = ClienteFalso(
        [
            [
                item("202600000001", "99.999,96", "0,00", "0,00"),
                item("202644380004", "10,00", "10,00", "10,00"),
            ]
        ],
        {"202644380004": item("202644380004", "10,00", "10,00", "10,00")},
    )

    preparados = varrer(cliente)

    assert cliente.releituras == ["202644380004"] * emendas_mod.CONFERENCIAS_POR_EMENDA
    suspeita = preparados[-1]
    assert suspeita["committed_value"] == Decimal("10.00")
    assert suspeita["_nao_confirmados"] == frozenset({"committed_value"})
    assert emendas_mod._travas["sem_desempate"] == 1


def test_segunda_releitura_resolve_quando_a_primeira_falha(limpar_travas):
    cliente = ClienteFalso(
        [
            [
                item("202600000001", "99.999,96", "0,00", "0,00"),
                item("202644380004", "10,00", "10,00", "10,00"),
            ]
        ],
        {
            "202644380004": [
                item("202644380004", "10,00", "10,00", "10,00"),
                item("202644380004", "100.000,00", "100.000,00", "100.000,00"),
            ]
        },
    )

    preparados = varrer(cliente)

    assert len(cliente.releituras) == 2
    assert preparados[-1]["committed_value"] == Decimal("100000.00")
    assert emendas_mod._travas["desempatado"] == 1


def test_releitura_indisponivel_nao_derruba_a_coleta(limpar_travas):
    cliente = ClienteFalso(
        [
            [
                item("202600000001", "99.999,96", "0,00", "0,00"),
                item("202644380004", "10,00", "10,00", "10,00"),
            ]
        ],
        {"202644380004": None},
    )

    preparados = varrer(cliente)

    assert emendas_mod._travas["releitura_indisponivel"] == 1
    assert emendas_mod._travas["sem_desempate"] == 1
    assert preparados[-1]["_nao_confirmados"] == frozenset({"committed_value"})


def test_valor_dividido_nao_rebaixa_a_referencia_de_ordem(limpar_travas):
    """Se um dividido virasse a nova referencia, todos os itens seguintes
    passariam a parecer normais e a deteccao morreria no meio do ano."""
    cliente = ClienteFalso(
        [
            [
                item("202600000001", "5.000.000,00", "0,00", "0,00"),
                item("202600000002", "500,00", "0,00", "0,00"),  # 5 milhoes dividido
                item("202600000003", "600,00", "0,00", "0,00"),  # 6 milhoes dividido
            ]
        ],
        {
            "202600000002": item("202600000002", "5.000.000,00", "0,00", "0,00"),
            "202600000003": item("202600000003", "6.000.000,00", "0,00", "0,00"),
        },
    )

    varrer(cliente)

    assert sorted(cliente.releituras) == ["202600000002", "202600000003"]
    assert emendas_mod._travas["desempatado"] == 2


def test_referencia_de_ordem_nao_sobe_com_valor_sem_desempate(limpar_travas):
    """Sem desempate o payload fica com o valor dividido, mas a referencia tem de
    continuar sendo a do item anterior."""
    cliente = ClienteFalso(
        [
            [
                item("202600000001", "5.000.000,00", "0,00", "0,00"),
                item("202600000002", "500,00", "0,00", "0,00"),
                item("202600000003", "600,00", "0,00", "0,00"),
            ]
        ],
        {"202600000002": None, "202600000003": None},
    )

    varrer(cliente)

    # Os dois seguintes continuaram sendo marcados, ou seja a referencia ficou
    # nos 5 milhoes em vez de cair para 500.
    assert emendas_mod._travas["suspeitos"] == 2


def test_teto_de_releituras_para_de_gastar_requisicao_sem_aceitar_suspeito(
    monkeypatch, limpar_travas
):
    """Em dia ruim da fonte, metade do ano vira suspeito. O teto impede a corrida
    infinita — mas quem sobra sem desempate preserva o gravado, nao entra como
    valor dividido em silencio."""
    monkeypatch.setattr(emendas_mod, "MAX_RELEITURAS_POR_RUN", 2)
    cliente = ClienteFalso(
        [
            [item("202600000001", "5.000.000,00", "0,00", "0,00")]
            + [item(f"20260000001{n}", "500,00", "0,00", "0,00") for n in range(3)]
        ],
        {f"20260000001{n}": None for n in range(3)},
    )

    preparados = varrer(cliente)

    assert len(cliente.releituras) == 2
    assert emendas_mod._travas["teto_avisado"] == 1
    assert all(
        p["_nao_confirmados"] == frozenset({"committed_value"})
        for p in preparados[1:]
    )
