"""Orquestrador de backfill histórico de votações e discursos (Câmara + Senado).

Mesma filosofia do `backfill_propositions`: roda em fatias pequenas, de hora em
hora via cron, registrando o progresso num arquivo de estado. É "deixa rodando e
esquece" — quando termina, apenas avisa que não há mais nada a fazer.

Por que um orquestrador separado dos crawlers: cada um dos 4 crawlers de
votos/discursos roda a invocação inteira dentro de UMA transação de banco (um
único `with session_scope()`). Rodar "todos os parlamentares × todos os anos" de
uma vez seria uma transação gigante — lenta e que perde tudo se estourar o
timeout. Aqui cada fatia é o menor recorte que o crawler aceita, então cada chunk
é uma transação curta e isolada (subprocesso próprio): se um falha, os já
concluídos permanecem salvos e o que falhou é tentado de novo na próxima rodada.

Recortes (fatias):
  - Votos Câmara:     janela trimestral (--data-inicio/--data-fim), SINCE_YEAR→hoje.
  - Votos Senado:     um por senador (--parliamentarian-code + --start/--end-date).
  - Discursos Câmara: um por deputado (--deputado-id + --data-inicio).
  - Discursos Senado: um por (senador, ano) (--parliamentarian + --year). Este roda
                      spaCy inline (NLP), é o mais pesado — por isso a fatia é a
                      menor possível: um senador, um ano.

Garantias para rodar sozinho (iguais ao backfill de proposições):
  - Trava de arquivo (flock): se um backfill ainda está rodando quando o cron
    dispara de novo, a nova execução sai na hora — nunca há dois batendo na mesma
    API ao mesmo tempo.
  - Timeout por chunk só como rede de segurança (processo genuinamente travado).

Uso:
    python -m mamute_scrappers.scripts.backfill_votes_speeches
    python -m mamute_scrappers.scripts.backfill_votes_speeches --chunks-per-run 3
    python -m mamute_scrappers.scripts.backfill_votes_speeches --status
"""

from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger("backfill_votes_speeches")

# --- Configuração -----------------------------------------------------------
SINCE_YEAR = 2018          # piso alinhado com backfill_propositions.py (Senado discursos 2018-2021 estavam ausentes)
BACKFILL_END_YEAR = date.today().year
CHUNKS_PER_RUN = 4         # chunks processados por execução do cron (conservador:
                           # o servidor é compartilhado e queremos ser educados
                           # com as APIs da Câmara/Senado)
CHUNK_TIMEOUT_SECONDS = 7200  # rede de segurança por chunk (2h); uma fatia
                              # termina muito antes — só pega processo travado.

STATE_FILE = Path(os.getenv("BACKFILL_VS_STATE_FILE", "/app/state/backfill_votes_speeches.json"))
LOCK_FILE = STATE_FILE.with_name("backfill_votes_speeches.lock")


# --- Estado -----------------------------------------------------------------
def _load_state() -> Dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Estado ilegível (%s); recomeçando do zero.", exc)
    return {"done": [], "updated_at": None}


def _save_state(state: Dict[str, Any]) -> None:
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


# --- Códigos de parlamentares (lidos do banco) ------------------------------
def _parliamentarian_codes(house: str) -> List[int]:
    """Códigos de parlamentares de uma casa. house ∈ {'Senador','Deputado'}."""
    from mamute_scrappers.db import session_scope
    from mamute_scrappers.db.models import Parliamentarian

    with session_scope() as session:
        rows = (
            session.query(Parliamentarian.parliamentarian_code)
            .filter(
                Parliamentarian.type == house,
                Parliamentarian.parliamentarian_code.isnot(None),
            )
            .all()
        )
    return sorted({int(code) for (code,) in rows})


# --- Construção dos chunks --------------------------------------------------
def _camara_votes_chunks() -> List[Dict[str, Any]]:
    """Votos da Câmara em janelas trimestrais (sem --parliamentarian na API; a
    única forma de fatiar é por data, daí o --data-fim que adicionamos ao crawler).
    Do trimestre mais recente para o mais antigo."""
    today = date.today()
    chunks: List[Dict[str, Any]] = []
    for year in range(BACKFILL_END_YEAR, SINCE_YEAR - 1, -1):
        for quarter in (4, 3, 2, 1):
            start = date(year, 3 * (quarter - 1) + 1, 1)
            if start > today:
                continue
            end = date(year, 12, 31) if quarter == 4 else date(year, 3 * quarter + 1, 1) - timedelta(days=1)
            end = min(end, today)
            chunks.append(
                {
                    "id": f"cam-votes-{year}Q{quarter}",
                    "kind": "camara_votes",
                    "data_inicio": start.isoformat(),
                    "data_fim": end.isoformat(),
                }
            )
    return chunks


def _senado_votes_chunks() -> List[Dict[str, Any]]:
    """Votos do Senado: um chunk por senador, cobrindo SINCE_YEAR→hoje."""
    start = date(SINCE_YEAR, 1, 1).isoformat()
    end = date.today().isoformat()
    return [
        {
            "id": f"sen-votes-{code}-since{SINCE_YEAR}",
            "kind": "senado_votes",
            "code": code,
            "start_date": start,
            "end_date": end,
        }
        for code in _parliamentarian_codes("Senador")
    ]


def _camara_speeches_chunks() -> List[Dict[str, Any]]:
    """Discursos da Câmara: um chunk por deputado, desde SINCE_YEAR."""
    start = date(SINCE_YEAR, 1, 1).isoformat()
    return [
        {
            "id": f"cam-speech-{code}-since{SINCE_YEAR}",
            "kind": "camara_speeches",
            "code": code,
            "data_inicio": start,
        }
        for code in _parliamentarian_codes("Deputado")
    ]


def _senado_speeches_chunks() -> List[Dict[str, Any]]:
    """Discursos do Senado: um chunk por (senador, ano) — o mais pesado (NLP)."""
    codes = _parliamentarian_codes("Senador")
    chunks: List[Dict[str, Any]] = []
    for year in range(BACKFILL_END_YEAR, SINCE_YEAR - 1, -1):
        for code in codes:
            chunks.append(
                {
                    "id": f"sen-speech-{code}-{year}",
                    "kind": "senado_speeches",
                    "code": code,
                    "year": year,
                }
            )
    return chunks


def _build_chunks() -> List[Dict[str, Any]]:
    """Intercala as quatro listas (round-robin) para que votos e discursos das
    duas casas avancem juntos ao longo das execuções, em vez de terminar uma
    categoria inteira antes de começar a próxima."""
    lists = [
        _camara_votes_chunks(),
        _senado_votes_chunks(),
        _camara_speeches_chunks(),
        _senado_speeches_chunks(),
    ]
    ordered: List[Dict[str, Any]] = []
    longest = max((len(lst) for lst in lists), default=0)
    for i in range(longest):
        for lst in lists:
            if i < len(lst):
                ordered.append(lst[i])
    return ordered


# --- Execução de um chunk ---------------------------------------------------
def _chunk_command(chunk: Dict[str, Any]) -> List[str]:
    kind = chunk["kind"]
    if kind == "camara_votes":
        return [
            sys.executable, "-m", "mamute_scrappers.camara_crawler.roll_call_votes",
            "--data-inicio", chunk["data_inicio"],
            "--data-fim", chunk["data_fim"],
        ]
    if kind == "senado_votes":
        return [
            sys.executable, "-m", "mamute_scrappers.senado_crawler.roll_call_votes",
            "--parliamentarian-code", str(chunk["code"]),
            "--start-date", chunk["start_date"],
            "--end-date", chunk["end_date"],
        ]
    if kind == "camara_speeches":
        return [
            sys.executable, "-m", "mamute_scrappers.camara_crawler.speeches_transcripts",
            "--deputado-id", str(chunk["code"]),
            "--data-inicio", chunk["data_inicio"],
        ]
    if kind == "senado_speeches":
        return [
            sys.executable, "-m", "mamute_scrappers.senado_crawler.speechs_transcipts",
            "--parliamentarian", str(chunk["code"]),
            "--year", str(chunk["year"]),
        ]
    raise ValueError(f"Tipo de chunk desconhecido: {kind}")


def _run_chunk(chunk: Dict[str, Any]) -> bool:
    cmd = _chunk_command(chunk)
    env = {**os.environ, "SQLALCHEMY_ECHO": "0", "PYTHONPATH": "/app"}
    logger.info("Chunk %s: iniciando (%s)", chunk["id"], " ".join(cmd[2:]))
    try:
        result = subprocess.run(
            cmd, cwd="/app", env=env,
            timeout=CHUNK_TIMEOUT_SECONDS,
            capture_output=True, text=True,
        )
    except subprocess.TimeoutExpired:
        logger.error("Chunk %s: estourou o timeout de %ss", chunk["id"], CHUNK_TIMEOUT_SECONDS)
        return False
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-5:]
        logger.error("Chunk %s: falhou (rc=%s). Fim do log:\n%s",
                     chunk["id"], result.returncode, "\n".join(tail))
        return False
    summary = next(
        (ln for ln in reversed((result.stdout or "").splitlines())
         if "conclu" in ln.lower() or "sincroniza" in ln.lower()),
        "",
    )
    logger.info("Chunk %s: concluído.%s", chunk["id"],
                f" {summary.strip()}" if summary else "")
    return True


# --- Main -------------------------------------------------------------------
def _acquire_lock():
    """Trava exclusiva não-bloqueante. Retorna o fd se conseguir, senão None."""
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd = open(LOCK_FILE, "w")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fd.close()
        return None
    return fd


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill histórico de votações e discursos em fatias.")
    parser.add_argument("--chunks-per-run", type=int, default=CHUNKS_PER_RUN,
                        help=f"Chunks por execução (padrão: {CHUNKS_PER_RUN}).")
    parser.add_argument("--status", action="store_true",
                        help="Apenas mostra o progresso e sai.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    state = _load_state()
    done = set(state.get("done", []))
    chunks = _build_chunks()
    pending = [c for c in chunks if c["id"] not in done]

    logger.info("Backfill votos/discursos: %s/%s chunks concluídos, %s pendentes.",
                len(done), len(chunks), len(pending))

    if args.status:
        return

    if not pending:
        logger.info("Backfill completo — nada a fazer. (Pode remover o cron de backfill_votes_speeches.)")
        return

    lock_fd = _acquire_lock()
    if lock_fd is None:
        logger.info("Outro backfill de votos/discursos já está em execução; saindo sem fazer nada.")
        return

    try:
        processed = 0
        for chunk in pending[: args.chunks_per_run]:
            if _run_chunk(chunk):
                done.add(chunk["id"])
                state["done"] = sorted(done)
                _save_state(state)
                processed += 1
            # Em caso de falha, o chunk continua pendente e é tentado na próxima execução.

        logger.info("Execução concluída: %s chunk(s) processado(s) nesta rodada. "
                    "Restam %s pendentes.", processed, len(pending) - processed)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()


if __name__ == "__main__":
    main()
