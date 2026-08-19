"""Orquestrador de backfill da cota parlamentar (2022 -> ano corrente) — CS-57.

Mesma mecanica dos backfills de proposicoes e emendas: cada execucao processa
poucos chunks e registra o progresso em arquivo de estado, o cron horario
esvazia a fila sozinho e depois vira no-op.

Cada chunk e um ano de UMA casa (cota-camara-2022, cota-senado-2022, ...),
intercalado por ano para o perfil ganhar cobertura das duas casas junto. Um
chunk da Camara e 1 download de ~8 MB + ~208 mil upserts (minutos, sem rate
limit); o do Senado e 1 GET de ~24 mil itens. A fila de 2022->2026 tem 10
chunks e fecha em poucas execucoes.

Cada chunk roda como subprocesso separado (transacao isolada): se um ano
falha, os concluidos permanecem e o que falhou volta na proxima execucao.

Uso:
    python -m mamute_scrappers.scripts.backfill_cota
    python -m mamute_scrappers.scripts.backfill_cota --chunks-per-run 4
    python -m mamute_scrappers.scripts.backfill_cota --status
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

logger = logging.getLogger("backfill_cota")

# --- Configuracao -----------------------------------------------------------
SINCE_YEAR = 2022
BACKFILL_END_YEAR = date.today().year
CHUNKS_PER_RUN = 2
# Um chunk da Camara processa ~208 mil linhas locais; medido bem abaixo de
# 1h. O timeout e rede de seguranca contra rede presa no download.
CHUNK_TIMEOUT_SECONDS = 3600

_MODULES = (
    ("camara", "mamute_scrappers.camara_crawler.expenses"),
    ("senado", "mamute_scrappers.senado_crawler.expenses"),
)

STATE_FILE = Path(
    os.getenv("BACKFILL_COTA_STATE_FILE", "/app/state/backfill_cota.json")
)
LOCK_FILE = STATE_FILE.with_name("backfill_cota.lock")


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
    """Um chunk por ano x casa, intercalado por ano (Camara, Senado, ...)."""
    return [
        {"key": f"cota-{house}-{year}", "ano": year, "module": module}
        for year in range(since_year, end_year + 1)
        for house, module in _MODULES
    ]


def _run_chunk(chunk: Dict[str, Any]) -> bool:
    cmd = [sys.executable, "-m", chunk["module"], "--ano", str(chunk["ano"])]
    logger.info("Chunk %s: %s", chunk["key"], " ".join(cmd))
    try:
        result = subprocess.run(cmd, timeout=CHUNK_TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired:
        logger.error("Chunk %s estourou o timeout.", chunk["key"])
        return False
    return result.returncode == 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Backfill da cota parlamentar.")
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
        logger.info("Backfill de cota completo — nada a fazer.")
        return

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK_FILE, "w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            logger.info("Outro backfill de cota ainda roda; saindo.")
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
        logger.info("Backfill de cota completo.")
    else:
        logger.info("Restam %s chunks.", restantes)


if __name__ == "__main__":
    main()
