"""Coleta dos planos de acao das emendas Pix e da prestacao de contas.

O campo `numero_emenda_parlamentar_plano_acao` da fonte E o nosso
`amendment_code`: casou em 300 de 300 emendas Pix numa amostra aleatoria de
2026-08-12. A relacao e 1:N — uma emenda se desdobra em varios planos de acao,
um por ente beneficiario (mediana 8, maximo medido 100, 57.827 planos no
total).

A prestacao de contas vive em duas tabelas da fonte:

* `relatorio_gestao_novo_especial` — regime atual, 42,8% dos planos. Traz tipo
  (Parcial/Final), situacao, valor executado e valor pendente.
* `relatorio_gestao_especial` — legado, 6,4%, seca a partir de 2025. So tem
  situacao.

Uniao medida: 44,2% dos planos, e 77,3% das emendas tem ao menos um plano
prestando contas.

ATENCAO EDITORIAL: ausencia de prestacao NAO e sonegacao. A cobertura por ano
do plano e 58% (2022), 57% (2023), 56% (2024), 46% (2025) e 6% (2026) — o
buraco do ano corrente e prazo em aberto, nao omissao. Quem exibe esse dado
tem de distinguir os dois casos; ver `textoPrestacao` no front.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from contextlib import nullcontext
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mamute_scrappers.transferegov_crawler.client import (  # noqa: E402
    TransferegovClient,
)

logger = logging.getLogger(__name__)

CENTS = Decimal("0.01")
COMMIT_EVERY = 500

TABELA_PLANOS = "plano_acao_especial"
TABELA_RELATORIO_NOVO = "relatorio_gestao_novo_especial"
TABELA_RELATORIO_LEGADO = "relatorio_gestao_especial"

CAMPOS_NOVO = {
    "situacao": "situacao_relatorio_gestao_novo",
    "tipo": "tipo_relatorio_gestao_novo",
    "valor_executado": "valor_executado_relatorio_gestao_novo",
    "valor_pendente": "valor_pendente_relatorio_gestao_novo",
    "data": "data_e_hora_relatorio_gestao_novo",
}

# Tudo que o robo reescreve a cada execucao. A fonte e a unica dona destes
# dados — nao ha correcao manual a preservar, diferente das emendas.
_ATUALIZAVEIS = (
    "codigo_plano_acao",
    "amendment_code",
    "ano",
    "situacao",
    "beneficiario_nome",
    "beneficiario_cnpj",
    "beneficiario_uf",
    "valor_custeio",
    "valor_investimento",
    "prestacao_situacao",
    "prestacao_tipo",
    "prestacao_valor_executado",
    "prestacao_valor_pendente",
    "prestacao_data",
    "prestacao_origem",
)


def _modelo() -> Any:
    """Import tardio: o teste troca esta funcao por um modelo local."""
    from mamute_scrappers.db.models import AmendmentActionPlan

    return AmendmentActionPlan


def _to_decimal(value: Any) -> Optional[Decimal]:
    """Converte para Decimal com 2 casas, passando por str.

    Passar por str evita a expansao binaria de Decimal(float): a fonte manda
    numero JSON, e dinheiro publico nao pode perder centavo.
    """
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(CENTS)
    except (InvalidOperation, ValueError):
        return None


def _texto(value: Any) -> Optional[str]:
    if value is None:
        return None
    limpo = " ".join(str(value).split())
    return limpo or None


def escolher_relatorio(
    relatorios: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """O relatorio mais forte do plano.

    Precedencia: `Final` vence `Parcial`; mesmo tipo, vence o mais recente por
    data; empatado nisso, `novo` vence `legado`.

    Guardar so o mais forte basta porque a fonte tem 1,02 relatorio por plano
    (1.725 relatorios para 1.685 planos). Se um dia quisermos serie historica,
    a migration e aditiva.
    """
    if not relatorios:
        return None

    def chave(r: Dict[str, Any]) -> tuple:
        return (
            1 if (r.get("tipo") or "").strip().lower() == "final" else 0,
            r.get("data") or "",
            1 if r.get("origem") == "novo" else 0,
        )

    return max(relatorios, key=chave)


def normalizar_relatorios(
    novos: Optional[List[Dict[str, Any]]],
    legados: Optional[List[Dict[str, Any]]],
) -> Dict[int, List[Dict[str, Any]]]:
    """Indexa os relatorios das duas tabelas da fonte por `id_plano_acao`."""
    idx: Dict[int, List[Dict[str, Any]]] = {}

    for linha in novos or []:
        idx.setdefault(linha["id_plano_acao"], []).append(
            {
                "origem": "novo",
                "situacao": linha.get(CAMPOS_NOVO["situacao"]),
                "tipo": linha.get(CAMPOS_NOVO["tipo"]),
                "valor_executado": _to_decimal(
                    linha.get(CAMPOS_NOVO["valor_executado"])
                ),
                "valor_pendente": _to_decimal(
                    linha.get(CAMPOS_NOVO["valor_pendente"])
                ),
                "data": linha.get(CAMPOS_NOVO["data"]),
            }
        )

    for linha in legados or []:
        # O legado so tem situacao: nao traz tipo, valor nem data.
        idx.setdefault(linha["id_plano_acao"], []).append(
            {
                "origem": "legado",
                "situacao": linha.get("situacao_relatorio_gestao"),
                "tipo": None,
                "valor_executado": None,
                "valor_pendente": None,
                "data": None,
            }
        )

    return idx


def build_plan_payload(
    plano: Dict[str, Any], relatorio: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Converte o plano cru da fonte na linha que a tabela espera."""
    return {
        "id_plano_acao": plano.get("id_plano_acao"),
        "codigo_plano_acao": _texto(plano.get("codigo_plano_acao")),
        "amendment_code": _texto(
            plano.get("numero_emenda_parlamentar_plano_acao")
        ),
        "ano": plano.get("ano_plano_acao"),
        "situacao": _texto(plano.get("situacao_plano_acao")),
        "beneficiario_nome": _texto(plano.get("nome_beneficiario_plano_acao")),
        "beneficiario_cnpj": _texto(plano.get("cnpj_beneficiario_plano_acao")),
        "beneficiario_uf": _texto(plano.get("uf_beneficiario_plano_acao")),
        "valor_custeio": _to_decimal(plano.get("valor_custeio_plano_acao")),
        "valor_investimento": _to_decimal(
            plano.get("valor_investimento_plano_acao")
        ),
        "prestacao_situacao": _texto(relatorio.get("situacao"))
        if relatorio
        else None,
        "prestacao_tipo": _texto(relatorio.get("tipo")) if relatorio else None,
        "prestacao_valor_executado": relatorio.get("valor_executado")
        if relatorio
        else None,
        "prestacao_valor_pendente": relatorio.get("valor_pendente")
        if relatorio
        else None,
        "prestacao_data": _texto(relatorio.get("data")) if relatorio else None,
        "prestacao_origem": relatorio.get("origem") if relatorio else None,
    }


def upsert_plan(session: Any, payload: Dict[str, Any]) -> tuple:
    """Grava ou atualiza um plano, casando pela chave natural da fonte.

    Plano cujo `amendment_code` nao existe em `parliamentary_amendment` e
    gravado assim mesmo: a coleta do Portal pode estar atras, e perder o plano
    seria pior que guardar a referencia pendente.
    """
    modelo = _modelo()

    registro = session.get(modelo, payload["id_plano_acao"])
    if registro is None:
        session.add(modelo(**payload))
        return payload["id_plano_acao"], True

    for campo in _ATUALIZAVEIS:
        setattr(registro, campo, payload.get(campo))
    return registro, False


def coletar(
    client: Optional[TransferegovClient] = None,
    persist: bool = True,
    limite: Optional[int] = None,
) -> Dict[str, Any]:
    """Traz os planos de acao e a prestacao de contas, e grava.

    Refaz a tabela inteira a cada execucao: sao ~58 requisicoes paginadas, e o
    upsert e idempotente. A primeira execucao ja e o backfill.
    """
    client = client or TransferegovClient()

    planos: List[Dict[str, Any]] = []
    for linha in client.iter_rows(TABELA_PLANOS):
        planos.append(linha)
        if limite is not None and len(planos) >= limite:
            break
    logger.info("Planos de acao lidos: %s", len(planos))

    ids = sorted({p["id_plano_acao"] for p in planos if p.get("id_plano_acao")})
    novos = client.fetch_in(TABELA_RELATORIO_NOVO, "id_plano_acao", ids)
    legados = client.fetch_in(TABELA_RELATORIO_LEGADO, "id_plano_acao", ids)
    por_plano = normalizar_relatorios(novos, legados)
    logger.info(
        "Prestacao de contas: %s planos de %s (%.1f%%)",
        len(por_plano),
        len(ids),
        100 * len(por_plano) / len(ids) if ids else 0,
    )

    if persist:
        from mamute_scrappers.db import session_scope

        contexto = session_scope()
    else:
        contexto = nullcontext(None)

    inseridos = 0
    atualizados = 0
    sem_emenda = 0
    por_ano: Counter = Counter()

    with contexto as session:
        for plano in planos:
            relatorio = escolher_relatorio(
                por_plano.get(plano.get("id_plano_acao"), [])
            )
            payload = build_plan_payload(plano, relatorio)
            if payload["id_plano_acao"] is None:
                continue
            if payload["amendment_code"] is None:
                sem_emenda += 1
            por_ano[payload["ano"]] += 1

            if session is None:
                continue

            _, criado = upsert_plan(session, payload)
            if criado:
                inseridos += 1
            else:
                atualizados += 1
            # Commit parcial: a tabela inteira numa transacao unica some se a
            # rede cair na ultima pagina. O upsert e idempotente, entao retomar
            # so reescreve o que ja estava.
            if (inseridos + atualizados) % COMMIT_EVERY == 0:
                session.commit()

    resumo = {
        "planos": len(planos),
        "com_prestacao": len(por_plano),
        "inseridos": inseridos,
        "atualizados": atualizados,
        "sem_codigo_de_emenda": sem_emenda,
        "por_ano": dict(sorted(por_ano.items(), key=lambda x: (x[0] is None, x[0]))),
    }
    logger.info("=== Planos de acao (Transferegov) ===")
    for chave, valor in resumo.items():
        logger.info("%s: %s", chave, valor)
    if sem_emenda:
        # Plano sem `numero_emenda_parlamentar_plano_acao` na fonte. Gravado
        # assim mesmo, com FK nula: nao da para ligar a emenda nenhuma.
        logger.info(
            "%s planos vieram sem codigo de emenda na fonte.", sem_emenda
        )
    if not persist:
        logger.info("Modo dry-run: nada foi gravado.")
    return resumo


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Le a fonte sem gravar."
    )
    parser.add_argument(
        "--limite", type=int, default=None, help="Corta a leitura em N planos."
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    coletar(persist=not args.dry_run, limite=args.limite)


if __name__ == "__main__":
    main()
