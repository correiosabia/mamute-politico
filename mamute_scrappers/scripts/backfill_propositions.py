"""Orquestrador de backfill histórico de proposições (Câmara + Senado).

Roda em fatias ("fracionadinho"): cada execução processa um número pequeno de
chunks e registra o progresso em um arquivo de estado. Pensado para rodar de
hora em hora via cron — o backfill completo acontece ao longo de ~1 dia sem
sobrecarregar o servidor nem a API de origem.

Cada chunk é executado como um subprocesso separado, ou seja, uma transação de
banco isolada: se um chunk falha, os já concluídos permanecem salvos e o que
falhou é tentado de novo na próxima execução.

Chunks:
  - Câmara: um por mês, de SINCE_YEAR até BACKFILL_END_YEAR (inclusive).
            Usa --data-inicio/--data-fim/--force-full.
  - Senado: um por senador. Usa --parliamentarian-code/--since-year.

Uso:
    python -m mamute_scrappers.scripts.backfill_propositions
    python -m mamute_scrappers.scripts.backfill_propositions --chunks-per-run 3
    python -m mamute_scrappers.scripts.backfill_propositions --status
"""

from __future__ import annotations

import argparse
import calendar
import json
import logging
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger("backfill_propositions")

# --- Configuração -----------------------------------------------------------
SINCE_YEAR = 2022          # ano mais antigo a buscar
BACKFILL_END_YEAR = 2024   # último ano do backfill (2025+ já está coberto e é
                           # mantido pelo cron incremental da Câmara)
CHUNKS_PER_RUN = 5         # chunks processados por execução do cron
CHUNK_TIMEOUT_SECONDS = 1800  # teto por chunk (30 min)

STATE_FILE = Path(os.getenv("BACKFILL_STATE_FILE", "/app/state/backfill.json"))


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


# --- Construção dos chunks --------------------------------------------------
def _senator_codes() -> List[int]:
    """Códigos de parlamentares do tipo Senador, lidos do banco."""
    from mamute_scrappers.db import session_scope
    from mamute_scrappers.db.models import Parliamentarian

    with session_scope() as session:
        rows = (
            session.query(Parliamentarian.parliamentarian_code)
            .filter(
                Parliamentarian.type == "Senador",
                Parliamentarian.parliamentarian_code.isnot(None),
            )
            .all()
        )
    return sorted({int(code) for (code,) in rows})


def _camara_month_chunks() -> List[Dict[str, Any]]:
    """Um chunk por mês, do mais recente para o mais antigo."""
    today = date.today()
    chunks: List[Dict[str, Any]] = []
    for year in range(BACKFILL_END_YEAR, SINCE_YEAR - 1, -1):
        for month in range(12, 0, -1):
            start = date(year, month, 1)
            if start > today:
                continue
            last_day = calendar.monthrange(year, month)[1]
            end = min(date(year, month, last_day), today)
            chunks.append(
                {
                    "id": f"camara-{year}-{month:02d}",
                    "kind": "camara",
                    "data_inicio": start.isoformat(),
                    "data_fim": end.isoformat(),
                    "year": year,
                }
            )
    return chunks


def _build_chunks() -> List[Dict[str, Any]]:
    """Lista completa de chunks, intercalando Câmara e Senado para que os dois
    avancem em paralelo ao longo das execuções."""
    camara = _camara_month_chunks()
    senado = [
        {"id": f"senado-{code}", "kind": "senado", "code": code}
        for code in _senator_codes()
    ]
    ordered: List[Dict[str, Any]] = []
    for i in range(max(len(camara), len(senado))):
        if i < len(camara):
            ordered.append(camara[i])
        if i < len(senado):
            ordered.append(senado[i])
    return ordered


# --- Execução de um chunk ---------------------------------------------------
def _chunk_command(chunk: Dict[str, Any]) -> List[str]:
    if chunk["kind"] == "camara":
        return [
            sys.executable, "-m", "mamute_scrappers.camara_crawler.proposition",
            "--year", str(chunk["year"]),
            "--data-inicio", chunk["data_inicio"],
            "--data-fim", chunk["data_fim"],
            "--force-full",
        ]
    if chunk["kind"] == "senado":
        return [
            sys.executable, "-m", "mamute_scrappers.senado_crawler.proposition",
            "--parliamentarian-code", str(chunk["code"]),
            "--since-year", str(SINCE_YEAR),
        ]
    raise ValueError(f"Tipo de chunk desconhecido: {chunk['kind']}")


def _run_chunk(chunk: Dict[str, Any]) -> bool:
    cmd = _chunk_command(chunk)
    # SQLALCHEMY_ECHO=0 mantém o log do backfill legível.
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
    logger.info("Chunk %s: concluído.", chunk["id"])
    return True


# --- Main -------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill histórico de proposições em fatias.")
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

    logger.info("Backfill: %s/%s chunks concluídos, %s pendentes.",
                len(done), len(chunks), len(pending))

    if args.status:
        return

    if not pending:
        logger.info("Backfill completo — nada a fazer. (Pode remover o cron de backfill.)")
        return

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


if __name__ == "__main__":
    main()
