"""Coleta de emendas parlamentares individuais do Portal da Transparencia.

Emenda orcamentaria (destinacao de verba), nao emenda a proposicao (alteracao
de texto de projeto de lei).

A fonte nao devolve identificador de parlamentar — so `nomeAutor` em texto
livre — entao cada emenda passa pelo casamento por nome de `author_matching`.
O que nao casa e persistido mesmo assim, com `parliamentarian_id` nulo e
`match_status` explicito, para ficar visivel no painel de auditoria.

A fonte tem um defeito de escala: devolve valor monetario dividido por 10.000 de
forma intermitente (ver `valores.py`). Por isso todo item passa por
`conferir_escala` antes de ser gravado, e o `upsert_amendment` ainda recusa, como
ultima trava, a escrita que encolhe um valor gravado em exatamente 10.000 vezes.
"""

from __future__ import annotations

import logging
import os
import sys
from collections import Counter
from contextlib import nullcontext
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mamute_scrappers.portal_crawler.author_matching import (  # noqa: E402
    MATCH_STATUS_MANUAL,
    MATCH_STATUS_MATCHED,
    MATCH_STATUS_UNMATCHED,
    ParliamentarianCandidate,
    match_author,
)
from mamute_scrappers.portal_crawler.client import (  # noqa: E402
    PortalTransparenciaClient,
)
from mamute_scrappers.portal_crawler.parsing import (  # noqa: E402
    is_individual_amendment,
    parse_brl,
)
from mamute_scrappers.portal_crawler.valores import (  # noqa: E402
    CAMPOS_MONETARIOS,
    detectar_suspeitos,
    encolheu_por_escala,
    mesclar_pelo_maior,
    resolvidos_por_prova,
)

logger = logging.getLogger(__name__)

API_KEY_ENV = "PORTAL_TRANSPARENCIA_API_KEY"
COMMIT_EVERY = 500


def _load_env_file() -> None:
    """Carrega o .env antes de ler a chave da API.

    Nada no processo carrega o .env sozinho: quem faz isso e `db/engine.py`, no
    import. Este crawler le a chave ANTES de tocar no banco, entao sem esta
    chamada a variavel nao existe em producao — onde a chave vive no arquivo, e
    nao no ambiente do container. Localmente o bug fica invisivel se a variavel
    for exportada na mao.

    `override=False` preserva variavel ja exportada no ambiente, mesma politica
    de db/engine.py.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover — dotenv e dependencia declarada
        return

    for env_file in (
        PROJECT_ROOT / "mamute_scrappers" / ".env",
        PROJECT_ROOT / ".env",
        Path.cwd() / ".env",
    ):
        if env_file.exists():
            load_dotenv(env_file, override=False)

ParliamentaryAmendment: Any = None

# Contadores das travas de escala. Vivem no modulo porque o upsert e chamado
# dentro do laco de `emendas()` e o relatorio sai no fim da mesma execucao;
# `emendas()` zera no inicio.
_travas: Counter = Counter()

# Quantas releituras por emenda suspeita antes de desistir do desempate. Duas
# bastam: a consulta por codigo erra ~3% das vezes, entao duas leituras ambiguas
# seguidas sao ~0,1% dos casos.
CONFERENCIAS_POR_EMENDA = 2

# Acima disto o log grita: 21% do ano de 2026 veio dividido na pior varredura
# medida, entao metade dos itens suspeitos e sinal de fonte em colapso, nao de
# dia normal.
TAXA_SUSPEITA_ALARMANTE = 0.5

# Teto de releituras por execucao, para o ano nao virar corrida infinita se a
# fonte quebrar em massa. 2.500 releituras a 2,2s = ~92 min, que somados aos ~15
# min da varredura cabem folgados no timeout de chunk do backfill. Ao estourar, o
# crawler nao passa a aceitar valor suspeito em silencio: para de gastar
# requisicao, marca o campo como nao confirmado (o gravado prevalece) e avisa no
# log.
MAX_RELEITURAS_POR_RUN = 2500

# Campos que o robo sempre atualiza, mesmo quando houve correcao manual de
# autoria: os valores financeiros mudam ao longo do ano inteiro.
_VALUE_FIELDS = (
    "year",
    "amendment_number",
    "amendment_type",
    "author_name_raw",
    "author_raw",
    "spending_locality",
    "function",
    "subfunction",
    "committed_value",
    "settled_value",
    "paid_value",
    "remainder_inscribed",
    "remainder_cancelled",
    "remainder_paid",
)


def _ensure_model() -> None:
    global ParliamentaryAmendment
    if ParliamentaryAmendment is not None:
        return
    from mamute_scrappers.db.models import (
        ParliamentaryAmendment as ParliamentaryAmendmentRuntime,
    )

    ParliamentaryAmendment = ParliamentaryAmendmentRuntime


def _coerce_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    cleaned = " ".join(str(value).split())
    return cleaned or None


def _parse_int(value: Any) -> Optional[int]:
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def build_payload(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Converte um item cru da API no dicionario que a tabela espera."""
    amendment_code = _coerce_text(item.get("codigoEmenda"))
    if not amendment_code:
        return None

    return {
        "amendment_code": amendment_code,
        "year": _parse_int(item.get("ano")),
        "amendment_number": _coerce_text(item.get("numeroEmenda")),
        "amendment_type": _coerce_text(item.get("tipoEmenda")),
        "author_name_raw": _coerce_text(item.get("nomeAutor")),
        "author_raw": _coerce_text(item.get("autor")),
        "spending_locality": _coerce_text(item.get("localidadeDoGasto")),
        "function": _coerce_text(item.get("funcao")),
        "subfunction": _coerce_text(item.get("subfuncao")),
        "committed_value": parse_brl(item.get("valorEmpenhado")),
        "settled_value": parse_brl(item.get("valorLiquidado")),
        "paid_value": parse_brl(item.get("valorPago")),
        "remainder_inscribed": parse_brl(item.get("valorRestoInscrito")),
        "remainder_cancelled": parse_brl(item.get("valorRestoCancelado")),
        "remainder_paid": parse_brl(item.get("valorRestoPago")),
    }


def upsert_amendment(session: Any, payload: Dict[str, Any]) -> Tuple[Any, bool]:
    """Grava ou atualiza uma emenda, casando pela chave natural do Portal.

    Os valores financeiros sempre sao atualizados, porque mudam ao longo do ano —
    exceto quando o valor novo e exatamente o gravado dividido por 10.000, a
    assinatura do bug de escala da fonte. Nesse caso o gravado prevalece: e a
    ultima trava, a que impede um run de estragar valor bom mesmo se todos os
    detectores anteriores falharem. Ver `valores.encolheu_por_escala`.

    Ja o vinculo com o parlamentar nao e sobrescrito quando `match_status` esta
    em `manual`: correcao humana prevalece sobre o robo.
    """
    if ParliamentaryAmendment is None:
        _ensure_model()

    record = (
        session.query(ParliamentaryAmendment)
        .filter(ParliamentaryAmendment.amendment_code == payload["amendment_code"])
        .one_or_none()
    )

    created = False
    if record is None:
        record = ParliamentaryAmendment(amendment_code=payload["amendment_code"])
        session.add(record)
        created = True

    # Campos que a conferencia da camada 3 nao conseguiu desempatar. Chave
    # privada, posta por `emendas()`; ausente quando o upsert e chamado direto.
    nao_confirmados = payload.get("_nao_confirmados") or frozenset()

    for field in _VALUE_FIELDS:
        novo = payload.get(field)

        if field in CAMPOS_MONETARIOS and field in nao_confirmados:
            # Numero sem prova nem desempate nao vai para o ar: em linha que ja
            # existe o valor gravado permanece; em linha nova o campo fica nulo
            # (a interface mostra "—") e o proximo run resolve.
            if not created:
                continue
            novo = None

        elif field in CAMPOS_MONETARIOS and not created:
            gravado = getattr(record, field)
            if encolheu_por_escala(gravado, novo):
                logger.warning(
                    "Emenda %s: %s viria %s contra %s gravado (divisao por "
                    "10.000 da fonte); mantendo o gravado.",
                    payload["amendment_code"],
                    field,
                    novo,
                    gravado,
                )
                _travas["escrita_recusada"] += 1
                continue

        setattr(record, field, novo)

    if record.match_status != MATCH_STATUS_MANUAL:
        record.parliamentarian_id = payload.get("parliamentarian_id")
        record.match_status = payload.get("match_status")

    if created:
        # Flush apos preencher os campos (match_status e NOT NULL). A sessao do
        # projeto usa autoflush=False e o commit so ocorre a cada COMMIT_EVERY;
        # sem este flush, um mesmo codigo repetido dentro do lote — e o Portal
        # repete registro entre paginas — nao seria encontrado pela consulta
        # acima, viraria duplicata e o commit morreria com UniqueViolation,
        # derrubando o ano inteiro.
        session.flush()

    return record, created


def _relatar_travas(individuais: int) -> None:
    """Fecha o log com o desempenho das travas de escala.

    Serve de termometro da fonte: se a taxa de suspeita disparar, o Portal esta
    tendo um dia ruim e o numero aparece aqui em vez de virar dado silencioso.
    """
    logger.info(
        "Travas de escala: %s suspeitos, %s desempatados por releitura, "
        "%s sem desempate, %s escritas recusadas, %s releituras gastas.",
        _travas["suspeitos"],
        _travas["desempatado"],
        _travas["sem_desempate"],
        _travas["escrita_recusada"],
        _travas["releituras"],
    )
    if _travas["releitura_indisponivel"]:
        logger.warning(
            "%s conferencias nao puderam ser lidas (falha de rede ou codigo "
            "ausente na resposta).",
            _travas["releitura_indisponivel"],
        )
    if individuais and _travas["suspeitos"] / individuais > TAXA_SUSPEITA_ALARMANTE:
        logger.warning(
            "Taxa de suspeita em %.1f%% dos itens (%s de %s) — acima de %.0f%%. "
            "A fonte esta devolvendo valor dividido em massa; confira o "
            "resultado antes de confiar nos totais do dia.",
            100 * _travas["suspeitos"] / individuais,
            _travas["suspeitos"],
            individuais,
            100 * TAXA_SUSPEITA_ALARMANTE,
        )


def conferir_escala(
    client: Any, payload: Dict[str, Any], maior_empenhado: Optional[Decimal]
) -> Tuple[Dict[str, Any], Optional[Decimal]]:
    """Aplica as camadas de deteccao a um item e devolve o payload conferido.

    Devolve tambem a nova referencia de ordem. Ela **so sobe**, e sempre com o
    valor final do payload: se a conferencia nao resolveu, um valor dividido nao
    pode rebaixar a referencia — senao todos os itens seguintes passariam a
    parecer normais e a deteccao morreria no meio do ano.
    """
    # Detectores de graca (ordem crescente da listagem e coerencia contabil),
    # descontando o que a prova estrutural absolve. So o que sobra custa
    # requisicao de conferencia.
    suspeitos = detectar_suspeitos(payload, maior_empenhado)
    suspeitos -= resolvidos_por_prova(payload, suspeitos)
    if suspeitos:
        _travas["suspeitos"] += 1
        payload = conferir_valores(client, payload, suspeitos)

    empenhado = payload.get("committed_value")
    if empenhado is not None and (
        maior_empenhado is None or empenhado > maior_empenhado
    ):
        maior_empenhado = empenhado

    return payload, maior_empenhado


def conferir_valores(
    client: Any, payload: Dict[str, Any], suspeitos: Set[str]
) -> Dict[str, Any]:
    """Desempata valor suspeito relendo a emenda pelo codigo (camada 3).

    Mescla pelo maior valor entre listagem e releitura — seguro porque o bug so
    subnotifica — e para assim que todos os campos suspeitos tiverem prova de
    integridade. Ou seja: para com prova, nao com estatistica.

    Nunca corrige por inferencia. Se `100.000,00` viria como `10,00` e nenhuma
    releitura confirma, nao gravamos `10,00 x 10.000`: marcamos o campo em
    `_nao_confirmados` e o upsert preserva o que ja estava.
    """
    codigo = payload["amendment_code"]
    pendentes = set(suspeitos)

    for _ in range(CONFERENCIAS_POR_EMENDA):
        if _travas["releituras"] >= MAX_RELEITURAS_POR_RUN:
            if not _travas["teto_avisado"]:
                _travas["teto_avisado"] = 1
                logger.warning(
                    "Teto de %s releituras atingido; os suspeitos restantes "
                    "ficam sem desempate e preservam o valor gravado.",
                    MAX_RELEITURAS_POR_RUN,
                )
            break
        _travas["releituras"] += 1
        item = client.fetch_amendment(codigo)
        if item is None:
            _travas["releitura_indisponivel"] += 1
            break

        confirmacao = build_payload(item)
        if confirmacao is None:
            break

        payload = mesclar_pelo_maior(payload, confirmacao)
        pendentes -= resolvidos_por_prova(payload, pendentes)
        if not pendentes:
            _travas["desempatado"] += 1
            return payload

    _travas["sem_desempate"] += 1
    logger.warning(
        "Emenda %s: %s sem desempate depois de %s releitura(s); preservando o "
        "valor gravado.",
        codigo,
        sorted(pendentes),
        CONFERENCIAS_POR_EMENDA,
    )
    payload = dict(payload)
    payload["_nao_confirmados"] = frozenset(pendentes)
    return payload


def _load_candidates() -> List[ParliamentarianCandidate]:
    from mamute_scrappers.db import session_scope
    from mamute_scrappers.db.models import Parliamentarian

    with session_scope() as session:
        rows = session.query(
            Parliamentarian.id,
            Parliamentarian.name,
            Parliamentarian.full_name,
        ).all()

    return [ParliamentarianCandidate(id=r[0], name=r[1], full_name=r[2]) for r in rows]


def emendas(
    *,
    ano: Optional[int] = None,
    persist: bool = True,
    dry_run_limit: Optional[int] = None,
) -> None:
    """Coleta emendas individuais de um ano, casa por nome e persiste."""
    ano = ano or date.today().year
    _load_env_file()
    _travas.clear()
    api_key = os.getenv(API_KEY_ENV, "")
    client = PortalTransparenciaClient(api_key)

    candidates = _load_candidates()
    logger.info("Base de parlamentares carregada: %s candidatos.", len(candidates))

    if persist:
        _ensure_model()
        from mamute_scrappers.db import session_scope

        session_context = session_scope()
    else:
        session_context = nullcontext(None)

    tipos_vistos: Counter = Counter()
    status_counter: Counter = Counter()
    maior_empenhado: Optional[Decimal] = None
    total = 0
    individuais = 0
    inserted = 0
    updated = 0
    exemplos_nao_casados: List[str] = []

    with session_context as session:
        for item in client.iter_amendments(ano):
            total += 1
            tipos_vistos[_coerce_text(item.get("tipoEmenda")) or "(vazio)"] += 1

            if not is_individual_amendment(item.get("tipoEmenda")):
                continue

            payload = build_payload(item)
            if payload is None:
                continue
            individuais += 1

            payload, maior_empenhado = conferir_escala(
                client, payload, maior_empenhado
            )

            result = match_author(payload["author_name_raw"], candidates)
            payload["parliamentarian_id"] = result.parliamentarian_id
            payload["match_status"] = result.status
            status_counter[result.status] += 1

            if (
                result.status == MATCH_STATUS_UNMATCHED
                and len(exemplos_nao_casados) < 20
            ):
                nome = payload["author_name_raw"]
                if nome and nome not in exemplos_nao_casados:
                    exemplos_nao_casados.append(nome)

            if session is not None:
                _, created = upsert_amendment(session, payload)
                if created:
                    inserted += 1
                else:
                    updated += 1
                # Commit parcial: `session_scope` so commita ao sair do bloco, e
                # um ano inteiro numa transacao unica (~6 mil linhas, medido)
                # some se a rede falhar na ultima das ~400 paginas. Como o
                # upsert e idempotente, retomar apenas reescreve o que ja estava.
                if (inserted + updated) % COMMIT_EVERY == 0:
                    session.commit()

            if dry_run_limit is not None and individuais >= dry_run_limit:
                break

    logger.info("=== Emendas %s ===", ano)
    logger.info("Total de emendas lidas: %s", total)
    logger.info("Emendas individuais: %s", individuais)
    logger.info("Valores de tipoEmenda vistos: %s", dict(tipos_vistos))
    logger.info("Casamento: %s", dict(status_counter))
    if individuais:
        taxa = 100 * status_counter.get(MATCH_STATUS_MATCHED, 0) / individuais
        logger.info("Taxa de casamento: %.1f%%", taxa)
    if exemplos_nao_casados:
        logger.info("Exemplos nao casados: %s", exemplos_nao_casados)
    _relatar_travas(individuais)
    if persist:
        logger.info("Persistencia: %s inseridas, %s atualizadas.", inserted, updated)
    else:
        logger.info("Modo dry-run: nada foi gravado.")


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description=(
            "Coleta emendas parlamentares individuais do Portal da Transparencia."
        )
    )
    parser.add_argument("--ano", type=int, help="Ano da coleta (default: ano corrente).")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nao persiste; apenas reporta o diagnostico.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Interrompe apos N emendas individuais (para diagnostico rapido).",
    )

    args = parser.parse_args()
    emendas(ano=args.ano, persist=not args.dry_run, dry_run_limit=args.limit)
