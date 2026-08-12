"""Travas contra o bug de escala da API de emendas (valor dividido por 10.000).

Os valores usados aqui sao pares reais medidos na fonte em 2026-08-12: a
listagem paginada devolveu o primeiro, a consulta por codigo e a pagina oficial
do Portal devolveram o segundo, no mesmo instante.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from mamute_scrappers.portal_crawler import valores

# (dividido pela fonte, verdadeiro) — codigos 202644380004, 202643680005,
# 202632680008, 202612710004, 202644480002.
PARES_REAIS = [
    (Decimal("10.00"), Decimal("100000.00")),
    (Decimal("207.00"), Decimal("2070000.00")),
    (Decimal("515.00"), Decimal("5150000.00")),
    (Decimal("70.00"), Decimal("700000.00")),
    (Decimal("700.00"), Decimal("7000000.00")),
    # Grande o bastante para o resultado da divisao passar por valor plausivel:
    # 17 milhoes viram 1.700, que nao chama atencao nenhuma.
    (Decimal("1700.00"), Decimal("17000000.00")),
]


@pytest.mark.parametrize(
    "valor",
    [
        Decimal("638087.12"),  # tem centavos
        Decimal("985.60"),
        Decimal("200000.00"),  # multiplo de 10.000
        Decimal("17000000.00"),
        Decimal("0.00"),  # 0 / 10.000 = 0
    ],
)
def test_prova_de_integridade_reconhece_valor_que_o_bug_nao_alcanca(valor):
    assert valores.veio_intacto(valor) is True


@pytest.mark.parametrize("valor", [Decimal("199995.00"), Decimal("7.00")])
def test_inteiro_nao_multiplo_de_10_mil_fica_sem_prova(valor):
    """Qualquer inteiro poderia, em tese, ser o resultado da divisao — basta o
    verdadeiro ser ele x 10.000. Sao os 199.995,00 e os 7,00 genuinos: quem os
    absolve e o detector de ordem, nao a prova estrutural."""
    assert valores.veio_intacto(valor) is False


@pytest.mark.parametrize("valor", [v for v, _ in PARES_REAIS])
def test_valor_dividido_nao_tem_prova_de_integridade(valor):
    """Todos os 1.134 corrompidos medidos eram inteiros e nao multiplos de
    10.000 — exatamente a classe que fica sem prova."""
    assert valores.veio_intacto(valor) is False


def test_prova_de_integridade_com_none():
    assert valores.veio_intacto(None) is False


@pytest.mark.parametrize("dividido, verdadeiro", PARES_REAIS)
def test_encolhimento_de_escala_e_reconhecido(dividido, verdadeiro):
    assert valores.encolheu_por_escala(verdadeiro, dividido) is True


@pytest.mark.parametrize(
    "antigo, novo",
    [
        # Queda legitima: empenho cancelado vai a zero, nao a 1/10.000.
        (Decimal("100000.00"), Decimal("0.00")),
        # Queda legitima de outra ordem de grandeza.
        (Decimal("100000.00"), Decimal("50000.00")),
        # Crescimento, o caso comum ao longo do ano.
        (Decimal("10.00"), Decimal("100000.00")),
        # Razao parecida, mas nao exata.
        (Decimal("100000.00"), Decimal("10.01")),
        (Decimal("100000.00"), Decimal("100.00")),
        (None, Decimal("10.00")),
        (Decimal("10.00"), None),
        # Zero e ponto fixo da divisao: 0/10.000 = 0. Sem esta guarda os tres
        # campos de resto, quase sempre "0,00", disparariam a trava em toda
        # linha do ano.
        (Decimal("0.00"), Decimal("0.00")),
    ],
)
def test_encolhimento_de_escala_nao_confunde_variacao_legitima(antigo, novo):
    assert valores.encolheu_por_escala(antigo, novo) is False


def test_detector_de_ordem_marca_valor_fora_de_posicao():
    """A listagem vem ordenada por valorEmpenhado crescente, e ordena pelo valor
    verdadeiro — o dividido cai quatro ordens de grandeza fora do lugar."""
    assert valores.suspeito_pela_ordem(Decimal("10.00"), Decimal("99999.96")) is True


def test_detector_de_ordem_aceita_sequencia_crescente():
    assert not valores.suspeito_pela_ordem(Decimal("100000.00"), Decimal("99999.96"))
    assert not valores.suspeito_pela_ordem(Decimal("100000.00"), Decimal("100000.00"))


def test_detector_de_ordem_ignora_valor_genuinamente_pequeno_no_inicio():
    """Existem emendas de R$ 7,00 de verdade (codigo 202643830011). Elas vem no
    comeco da ordenacao, onde nada as antecede, e nao podem ser marcadas."""
    assert valores.suspeito_pela_ordem(Decimal("7.00"), None) is False
    assert valores.suspeito_pela_ordem(Decimal("7.00"), Decimal("0.00")) is False


def test_detector_de_ordem_nao_dispara_em_quebra_sem_assinatura_de_escala():
    """Se a fonte mudar o criterio de ordenacao, uma quebra qualquer nao pode
    virar alarme em massa: so marca quando o x10.000 recolocaria no lugar."""
    assert valores.suspeito_pela_ordem(Decimal("5.00"), Decimal("9000000.00")) is False


def test_contabilidade_marca_empenhado_quando_liquidado_o_supera():
    """Caso real da emenda 202644380006: empenhado veio 20,00 e liquidado
    127,00. Nao se liquida mais do que se empenhou."""
    suspeitos = valores.suspeitos_pela_contabilidade(
        {
            "committed_value": Decimal("20.00"),
            "settled_value": Decimal("127.00"),
            "paid_value": Decimal("127.00"),
        }
    )
    assert suspeitos == {"committed_value"}


def test_contabilidade_marca_liquidado_quando_pago_o_supera():
    """Pega o campo que o detector de ordem nao ve: a listagem so e ordenada por
    valorEmpenhado."""
    suspeitos = valores.suspeitos_pela_contabilidade(
        {
            "committed_value": Decimal("2070000.00"),
            "settled_value": Decimal("43.00"),
            "paid_value": Decimal("430000.00"),
        }
    )
    assert suspeitos == {"settled_value"}


def test_contabilidade_aceita_liquidacao_de_resto_a_pagar():
    """Caso legitimo e observado (codigo 202632980010): empenhado zero no ano e
    liquidado alto, porque a liquidacao e de empenho de exercicio anterior."""
    suspeitos = valores.suspeitos_pela_contabilidade(
        {
            "committed_value": Decimal("0.00"),
            "settled_value": Decimal("1199610.20"),
            "paid_value": Decimal("0.00"),
        }
    )
    assert suspeitos == set()


def test_contabilidade_aceita_cadeia_coerente():
    suspeitos = valores.suspeitos_pela_contabilidade(
        {
            "committed_value": Decimal("11750950.00"),
            "settled_value": Decimal("8742394.62"),
            "paid_value": Decimal("8742394.62"),
        }
    )
    assert suspeitos == set()


def test_mescla_pelo_maior_eleva_o_campo_dividido():
    """O bug so subnotifica, entao entre duas leituras o maior valor nunca e o
    corrompido."""
    listagem = {
        "committed_value": Decimal("10.00"),
        "settled_value": Decimal("10.00"),
        "paid_value": Decimal("100000.00"),
        "remainder_inscribed": None,
        "amendment_code": "202644380004",
        "function": "Assistência social",
    }
    confirmacao = {
        "committed_value": Decimal("100000.00"),
        "settled_value": Decimal("100000.00"),
        "paid_value": Decimal("100000.00"),
        "remainder_inscribed": Decimal("0.00"),
        "function": "outra coisa",
    }

    mesclado = valores.mesclar_pelo_maior(listagem, confirmacao)

    assert mesclado["committed_value"] == Decimal("100000.00")
    assert mesclado["settled_value"] == Decimal("100000.00")
    assert mesclado["paid_value"] == Decimal("100000.00")
    assert mesclado["remainder_inscribed"] == Decimal("0.00")
    # Campo nao monetario nao e tocado: quem manda nele e a listagem.
    assert mesclado["function"] == "Assistência social"


def test_mescla_nao_rebaixa_quando_a_releitura_vem_dividida():
    listagem = {"committed_value": Decimal("100000.00")}
    confirmacao = {"committed_value": Decimal("10.00")}

    mesclado = valores.mesclar_pelo_maior(listagem, confirmacao)

    assert mesclado["committed_value"] == Decimal("100000.00")


def test_deteccao_conjunta_desconta_o_que_a_prova_absolve():
    """Valor multiplo de 10.000 fora de ordem nao gasta requisicao: a prova
    estrutural garante que aquela leitura nao passou pelo bug."""
    payload = {
        "committed_value": Decimal("200000.00"),
        "settled_value": Decimal("200000.00"),
        "paid_value": Decimal("200000.00"),
    }
    suspeitos = valores.detectar_suspeitos(payload, Decimal("9000000.00"))
    assert suspeitos - valores.resolvidos_por_prova(payload, suspeitos) == set()
