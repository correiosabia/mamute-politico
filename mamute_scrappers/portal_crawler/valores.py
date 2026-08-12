"""Defesas contra o bug de escala da API de emendas do Portal da Transparencia.

A fonte devolve, de forma intermitente, valores monetarios **divididos por
10.000**. Medido em 2026-08-12 numa varredura completa de 2026: 1.134 de 5.364
itens (21% do ano, 46,5% dos valores suscetiveis) vieram divididos. A mesma URL,
repetida, alterna entre certo e errado — nao e cache (todas as respostas vem
`x-cache: Miss`), nao e unidade documentada (o OpenAPI declara os seis campos
como `type: string`, sem formato nem descricao) e nao e o nosso parser
(`parse_brl` foi verificado com as strings reais). A propria pagina oficial do
Portal mostra o valor certo no mesmo instante em que a API devolve o dividido —
9 de 9 casos conferidos —, o que localiza o defeito na camada REST deles.

O bug tem duas propriedades que este modulo explora:

1. **So atinge multiplos exatos de 10.000.** Dos 1.134 corrompidos, zero tinham
   centavos e zero eram multiplos de 10.000. Ou seja: valor com centavos, ou
   valor multiplo de 10.000, e prova de que aquela leitura veio intacta.
2. **So subnotifica, nunca infla.** Entao entre duas leituras da mesma emenda o
   maior valor e sempre o mais proximo da verdade.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Iterable, Optional, Set, Tuple

# O bug divide por exatamente 10.000, sempre.
FATOR_ESCALA = Decimal(10_000)

# Ordem contabil: nao se liquida o que nao foi empenhado, nem se paga o que nao
# foi liquidado — dentro do mesmo exercicio.
CAMPOS_MONETARIOS: Tuple[str, ...] = (
    "committed_value",
    "settled_value",
    "paid_value",
    "remainder_inscribed",
    "remainder_cancelled",
    "remainder_paid",
)


def veio_intacto(valor: Optional[Decimal]) -> bool:
    """Prova de que este valor nao e resultado da divisao por 10.000.

    Duas provas, ambas por construcao:

    - **tem centavos**: dividir um multiplo de 10.000 por 10.000 sempre da
      inteiro, entao `638.087,12` nunca pode ser fruto do bug;
    - **e multiplo de 10.000**: o resultado da divisao so seria multiplo de
      10.000 se o valor verdadeiro passasse de R$ 100 milhoes e fosse multiplo
      de 10^8. Emenda individual nao chega la (o maior valor observado em 2026 e
      R$ 40 milhoes), e mesmo se chegasse a trava de escrita
      (`encolheu_por_escala`) ainda pegaria o caso.

    `None` nao e prova de nada. Zero e intacto: 0/10.000 = 0.
    """
    if valor is None:
        return False
    if valor % 1 != 0:
        return True
    return valor % FATOR_ESCALA == 0


def encolheu_por_escala(
    antigo: Optional[Decimal], novo: Optional[Decimal]
) -> bool:
    """Verdadeiro quando `novo` e exatamente `antigo` dividido por 10.000.

    E a assinatura exata do bug. Nao existe fato orcamentario que reduza um
    valor a 1/10.000 dele mantendo todos os digitos — um empenho cancelado vai a
    zero, nao a um decimo de milesimo.

    Zero fica fora: e ponto fixo da divisao (0/10.000 = 0), entao campo zerado
    que continua zerado nao e encolhimento nenhum. Sem esta guarda, os tres
    campos de resto — quase sempre `0,00` — disparariam a trava em toda linha.
    """
    if antigo is None or novo is None:
        return False
    if novo == 0:
        return False
    return novo * FATOR_ESCALA == antigo


def suspeito_pela_ordem(
    valor: Optional[Decimal], maior_visto: Optional[Decimal]
) -> bool:
    """Verdadeiro quando o valor quebra a ordem crescente da listagem *e* a
    multiplicacao por 10.000 recolocaria ele no lugar.

    A listagem paginada vem ordenada por `valorEmpenhado` crescente, e ordena
    pelo valor **verdadeiro** — o corrompido cai quatro ordens de grandeza fora
    de posicao. Na varredura de 2026 este detector marcou 1.134 itens e em
    1.134/1.134 o x10.000 restaurou a ordem.

    A segunda condicao existe para o detector nao virar um alarme falso em massa
    se a fonte mudar o criterio de ordenacao: sem a assinatura de escala, uma
    quebra de ordem qualquer nao e marcada aqui.
    """
    if valor is None or maior_visto is None:
        return False
    if valor >= maior_visto:
        return False
    return valor * FATOR_ESCALA >= maior_visto


def suspeitos_pela_contabilidade(payload: Dict[str, Any]) -> Set[str]:
    """Campos que a coerencia contabil denuncia como divididos.

    Liquidado maior que empenhado, ou pago maior que liquidado, e impossivel
    dentro do exercicio — a menos que o menor deles tenha vindo dividido. So
    marca quando a assinatura de escala explica a inversao, porque existe um caso
    legitimo de liquidado sem empenhado no ano: liquidacao de resto a pagar de
    exercicio anterior (observado na fonte com `valorEmpenhado` igual a zero).

    Complementa o detector de ordem: pega inversoes em `settled_value`, que a
    ordenacao da listagem nao cobre.
    """
    empenhado = payload.get("committed_value")
    liquidado = payload.get("settled_value")
    pago = payload.get("paid_value")

    suspeitos: Set[str] = set()

    def inversao(menor: Optional[Decimal], maior: Optional[Decimal]) -> bool:
        if menor is None or maior is None:
            return False
        if menor <= 0 or maior <= menor:
            return False
        return menor * FATOR_ESCALA >= maior

    if inversao(empenhado, liquidado) or inversao(empenhado, pago):
        suspeitos.add("committed_value")
    if inversao(liquidado, pago):
        suspeitos.add("settled_value")

    return suspeitos


def detectar_suspeitos(
    payload: Dict[str, Any], maior_empenhado_visto: Optional[Decimal]
) -> Set[str]:
    """Uniao dos detectores que nao custam requisicao."""
    suspeitos = suspeitos_pela_contabilidade(payload)
    if suspeito_pela_ordem(payload.get("committed_value"), maior_empenhado_visto):
        suspeitos.add("committed_value")
    return suspeitos


def mesclar_pelo_maior(
    payload: Dict[str, Any], confirmacao: Dict[str, Any]
) -> Dict[str, Any]:
    """Devolve `payload` com cada campo monetario elevado ao maior dos dois.

    Seguro porque o bug so subnotifica: entre duas leituras da mesma emenda, a
    maior nunca e a corrompida. Nao mexe nos campos nao monetarios — quem manda
    neles e a listagem, que e a leitura mais recente.
    """
    mesclado = dict(payload)
    for campo in CAMPOS_MONETARIOS:
        atual = payload.get(campo)
        outro = confirmacao.get(campo)
        if outro is None:
            continue
        if atual is None or outro > atual:
            mesclado[campo] = outro
    return mesclado


def resolvidos_por_prova(
    payload: Dict[str, Any], campos: Iterable[str]
) -> Set[str]:
    """Dos campos suspeitos, os que a prova estrutural absolve."""
    return {campo for campo in campos if veio_intacto(payload.get(campo))}


__all__ = [
    "CAMPOS_MONETARIOS",
    "FATOR_ESCALA",
    "detectar_suspeitos",
    "encolheu_por_escala",
    "mesclar_pelo_maior",
    "resolvidos_por_prova",
    "suspeito_pela_ordem",
    "suspeitos_pela_contabilidade",
    "veio_intacto",
]
