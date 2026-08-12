"""Orquestrador de backfill de emendas parlamentares (2022 -> ano corrente).

Mesma mecanica do backfill de proposicoes: cada execucao processa poucos chunks
e registra o progresso em arquivo de estado, de modo que o cron horario esvazia
a fila sozinho e depois vira no-op.

Cada chunk e um ano inteiro. Medido na fonte em 2026-08-06: ~400 paginas por
ano, ~15 min de coleta. A fila tem ~5 itens e fecha em cerca de 3 execucoes
horarias com --chunks-per-run 2 — bem mais curta que a de proposicoes, que leva
dias.

Cada chunk roda como subprocesso separado, ou seja transacao isolada: se um ano
falha, os ja concluidos permanecem salvos e o que falhou e tentado de novo na
proxima execucao.

Uso:
    python -m mamute_scrappers.scripts.backfill_emendas
    python -m mamute_scrappers.scripts.backfill_emendas --chunks-per-run 1
    python -m mamute_scrappers.scripts.backfill_emendas --status
"""

from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger("backfill_emendas")

# --- Configuracao -----------------------------------------------------------
SINCE_YEAR = 2022
BACKFILL_END_YEAR = date.today().year
CHUNKS_PER_RUN = 2
# Rede de seguranca. Um ano varre em ~15 min, mas em dia ruim da fonte as
# conferencias de escala do crawler (valor dividido por 10.000) somam ate ~92 min
# de releituras — ver MAX_RELEITURAS_POR_RUN em portal_crawler/emendas.py. Com
# 2h o chunk morreria justamente nos anos mais afetados e seria retentado para
# sempre.
CHUNK_TIMEOUT_SECONDS = 14400

STATE_FILE = Path(
    os.getenv("BACKFILL_EMENDAS_STATE_FILE", "/app/state/backfill_emendas.json")
)
LOCK_FILE = STATE_FILE.with_name("backfill_emendas.lock")


# --- Estado -----------------------------------------------------------------
def _load_state() -> Dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Estado ilegivel (%s); recomecando do zero.", exc)
    return {"done": [], "updated_at": None}


def _save_state(state: Dict[str, Any]) -> None:
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


# --- Chunks -----------------------------------------------------------------
def build_chunks(since_year: int, end_year: int) -> List[Dict[str, Any]]:
    """Um chunk por ano do intervalo, inclusive nas duas pontas."""
    return [
        {"key": f"emendas-{year}", "ano": year}
        for year in range(since_year, end_year + 1)
    ]


def _run_chunk(chunk: Dict[str, Any]) -> bool:
    cmd = [
        sys.executable,
        "-m",
        "mamute_scrappers.portal_crawler.emendas",
        "--ano",
        str(chunk["ano"]),
    ]
    logger.info("Chunk %s: %s", chunk["key"], " ".join(cmd))
    try:
        result = subprocess.run(cmd, timeout=CHUNK_TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired:
        logger.error("Chunk %s estourou o timeout.", chunk["key"])
        return False
    return result.returncode == 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Backfill de emendas parlamentares.")
    parser.add_argument("--chunks-per-run", type=int, default=CHUNKS_PER_RUN)
    parser.add_argument("--status", action="store_true", help="So mostra o progresso.")
    args = parser.parse_args()

    chunks = build_chunks(SINCE_YEAR, BACKFILL_END_YEAR)
    state = _load_state()
    done = set(state.get("done", []))
    pending = [c for c in chunks if c["key"] not in done]

    if args.status:
        logger.info("Progresso: %s/%s chunks concluidos.", len(done), len(chunks))
        for chunk in pending:
            logger.info("  pendente: %s", chunk["key"])
        return

    if not pending:
        logger.info("Backfill de emendas completo — nada a fazer.")
        return

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK_FILE, "w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            logger.info("Outro backfill de emendas ainda roda; saindo.")
            return

        for chunk in pending[: args.chunks_per_run]:
            if _run_chunk(chunk):
                done.add(chunk["key"])
                state["done"] = sorted(done)
                _save_state(state)
            else:
                logger.warning("Chunk %s falhou; sera tentado de novo.", chunk["key"])

    restantes = len([c for c in chunks if c["key"] not in done])
    if restantes == 0:
        logger.info("Backfill de emendas completo.")
    else:
        logger.info("Restam %s chunks.", restantes)


if __name__ == "__main__":
    main()
