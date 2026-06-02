"""Orquestrador de backfill da coluna `vote_date` em roll_call_votes.

Os votos históricos foram persistidos antes do `vote_date` existir, então
não têm a data real de votação populada (a UI cai pro `created_at`, que é
o dia da ingestão — daí cards exibindo "23/05/2026" pra votações antigas).

Estratégia:
  - Cada votação na API gera N linhas em `roll_call_votes` com o MESMO `link`.
    Logo, agrupando por link, ~221k votos da Câmara correspondem a ~5-10k
    votações distintas; idem para o Senado. Uma chamada HTTP por link.
  - Câmara: link = `.../api/v2/votacoes/{votacao_id}`. Pegamos
    `dataHoraRegistro` no `GET .../votacoes/{id}`.
  - Senado: link já é um endpoint do `legis.senado.leg.br/dadosabertos`.
    Fazemos GET no próprio link e procuramos `DataSessao` (ou variantes
    como `dataSessao`, `DataHoraInicio`) na resposta.

Garantias:
  - State file persistente (`backfill_vote_dates.json`) — re-execução idempotente.
  - Lock via flock — não roda duas vezes em paralelo.
  - `--chunks-per-run`: idem ao backfill_propositions; cron horário processa
    em fatias. Auto-encerra quando não há mais pendentes.
  - UPDATE com filtro `vote_date IS NULL`: votos já populados pelo crawler
    incremental (pós-migration) não são tocados.

Uso:
    python -m mamute_scrappers.scripts.backfill_vote_dates --status
    python -m mamute_scrappers.scripts.backfill_vote_dates --chunks-per-run 200
"""

from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests
from sqlalchemy import select, update as sa_update

logger = logging.getLogger("backfill_vote_dates")

REQUEST_DELAY = 0.1
DEFAULT_CHUNKS_PER_RUN = 100

STATE_FILE = Path(os.getenv(
    "VOTE_DATE_STATE_FILE", "/app/state/backfill_vote_dates.json"
))
LOCK_FILE = STATE_FILE.with_name("backfill_vote_dates.lock")

DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y",
)


def _load_state() -> dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Estado ilegível (%s); recomeçando do zero.", exc)
    return {"done": [], "failed": [], "updated_at": None}


def _save_state(state: dict[str, Any]) -> None:
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


def _acquire_lock():
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd = open(LOCK_FILE, "w")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fd.close()
        return None
    return fd


def _parse_date(value: Any) -> Optional[date]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _scan_for_date(obj: Any, keys: tuple[str, ...]) -> Optional[date]:
    """Procura a primeira data parseable sob qualquer chave em `keys`,
    em qualquer profundidade. Aceita variações de capitalização."""
    target = {k.lower() for k in keys}
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(key, str) and key.lower() in target:
                parsed = _parse_date(value)
                if parsed is not None:
                    return parsed
        for value in obj.values():
            found = _scan_for_date(value, keys)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _scan_for_date(item, keys)
            if found is not None:
                return found
    return None


def _request_json(url: str) -> Optional[Any]:
    headers = {"Accept": "application/json"}
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Falha no GET %s: %s", url, exc)
        return None
    try:
        return response.json()
    except ValueError as exc:
        logger.warning("JSON inválido em %s: %s", url, exc)
        return None


def _fetch_camara_date(link: str) -> Optional[date]:
    """Câmara: link = .../votacoes/{id}. GET retorna dados.dataHoraRegistro."""
    data = _request_json(link)
    if not isinstance(data, dict):
        return None
    dados = data.get("dados")
    if not isinstance(dados, dict):
        return None
    return _parse_date(dados.get("dataHoraRegistro"))


def _fetch_senado_date(link: str) -> Optional[date]:
    """Senado: o link já é um endpoint do legis.senado.leg.br. A resposta
    tem `DataSessao` em algum nível (formato YYYY-MM-DD HH:MM:SS)."""
    data = _request_json(link)
    if data is None:
        return None
    return _scan_for_date(
        data,
        keys=("DataSessao", "dataSessao", "DataHoraInicio", "dataHoraInicio"),
    )


def _resolve_fetcher(link: str):
    if "camara.leg.br" in link:
        return _fetch_camara_date
    if "senado.leg.br" in link:
        return _fetch_senado_date
    return None


def _list_pending_links(session, RollCallVote) -> list[str]:
    """DISTINCT links de roll_call_votes com vote_date NULL e link não-nulo."""
    rows = session.execute(
        select(RollCallVote.link)
        .where(RollCallVote.vote_date.is_(None))
        .where(RollCallVote.link.is_not(None))
        .group_by(RollCallVote.link)
    ).all()
    return [row[0] for row in rows if row[0]]


def _apply_vote_date(session, RollCallVote, link: str, vote_date: date) -> int:
    """UPDATE limitado a votos com vote_date NULL — não sobrescreve dados frescos."""
    result = session.execute(
        sa_update(RollCallVote)
        .where(RollCallVote.link == link)
        .where(RollCallVote.vote_date.is_(None))
        .values(vote_date=vote_date)
    )
    return result.rowcount or 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill da coluna vote_date em roll_call_votes."
    )
    parser.add_argument(
        "--chunks-per-run",
        type=int,
        default=DEFAULT_CHUNKS_PER_RUN,
        help=f"Links processados por execução (padrão: {DEFAULT_CHUNKS_PER_RUN}).",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Apenas mostra o progresso e sai.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    # Import tardio: o módulo de DB faz import-time work que não queremos no --help.
    from mamute_scrappers.db import session_scope
    from mamute_scrappers.db.models import RollCallVote

    state = _load_state()
    done = set(state.get("done", []))
    failed = set(state.get("failed", []))

    with session_scope() as session:
        pending_links = _list_pending_links(session, RollCallVote)

    pending = [link for link in pending_links if link not in done and link not in failed]

    logger.info(
        "Backfill vote_dates: %s links done, %s falhados, %s pendentes (total DB: %s).",
        len(done),
        len(failed),
        len(pending),
        len(pending_links),
    )

    if args.status:
        return

    if not pending:
        logger.info("Backfill vote_dates completo — nada a fazer.")
        return

    lock_fd = _acquire_lock()
    if lock_fd is None:
        logger.info("Outro backfill_vote_dates já está em execução; saindo.")
        return

    processed_ok = 0
    processed_fail = 0
    rows_updated_total = 0
    try:
        for link in pending[: args.chunks_per_run]:
            fetcher = _resolve_fetcher(link)
            if fetcher is None:
                logger.warning("Link %s sem origem reconhecida; marcado como falhado.", link)
                failed.add(link)
                processed_fail += 1
                continue

            vote_date = fetcher(link)
            if vote_date is None:
                logger.warning("Não obtive data para %s.", link)
                failed.add(link)
                processed_fail += 1
            else:
                with session_scope() as session:
                    rows = _apply_vote_date(session, RollCallVote, link, vote_date)
                rows_updated_total += rows
                logger.info("%s → %s (%s linhas)", link, vote_date.isoformat(), rows)
                done.add(link)
                processed_ok += 1

            state["done"] = sorted(done)
            state["failed"] = sorted(failed)
            _save_state(state)

            if REQUEST_DELAY > 0:
                time.sleep(REQUEST_DELAY)

        logger.info(
            "Execução concluída: %s links OK, %s falhados, %s votos atualizados. Restam %s pendentes.",
            processed_ok,
            processed_fail,
            rows_updated_total,
            max(0, len(pending) - processed_ok - processed_fail),
        )
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()


if __name__ == "__main__":
    main()
