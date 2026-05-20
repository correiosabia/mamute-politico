"""Orquestrador de backfill histórico de proposições (Câmara + Senado).

Roda em fatias ("fracionadinho"): cada execução processa um número pequeno de
chunks e registra o progresso em um arquivo de estado. Pensado para rodar de
hora em hora via cron — o backfill completo acontece ao longo de alguns dias
sem sobrecarregar o servidor nem a API de origem. É "deixa rodando e esquece":
quando termina, ele apenas avisa que não há mais nada a fazer.

Cada chunk é executado como um subprocesso separado, ou seja, uma transação de
banco isolada: se um chunk falha, os já concluídos permanecem salvos e o que
falhou é tentado de novo na próxima execução.

Garantias para rodar sozinho:
  - Trava de arquivo (flock): se um backfill ainda está rodando quando o cron
    dispara de novo, a nova execução sai na hora — nunca há dois batendo na
    mesma API ao mesmo tempo.
  - Timeout por chunk só como rede de segurança (processo genuinamente travado).

Chunks:
  - Câmara: uma janela de ~7 dias, de SINCE_YEAR até BACKFILL_END_YEAR.
            Usa --data-inicio/--data-fim (sem --force-full: proposições novas
            já trazem os detalhes; reprocessar tudo seria lento e inútil).
  - Senado: um por senador. Usa --parliamentarian-code/--since-year.

Uso:
    python -m mamute_scrappers.scripts.backfill_propositions
    python -m mamute_scrappers.scripts.backfill_propositions --chunks-per-run 3
    python -m mamute_scrappers.scripts.backfill_propositions --status
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

logger = logging.getLogger("backfill_propositions")

# --- Configuração -----------------------------------------------------------
SINCE_YEAR = 2018          # ano mais antigo a buscar
BACKFILL_END_YEAR = 2024   # último ano do backfill (2025+ já está coberto e é
                           # mantido pelo cron incremental da Câmara)
CHUNK_DAYS = 7             # tamanho da janela de cada chunk da Câmara (dias)
CHUNKS_PER_RUN = 5         # chunks processados por execução do cron
CHUNK_TIMEOUT_SECONDS = 7200  # rede de segurança por chunk (2h) — uma janela
                              # semanal termina muito antes disso; só pega
                              # processo realmente travado.

STATE_FILE = Path(os.getenv("BACKFILL_STATE_FILE", "/app/state/backfill.json"))
LOCK_FILE = STATE_FILE.with_name("backfill.lock")


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


def _camara_week_chunks() -> List[Dict[str, Any]]:
    """Janelas de ~7 dias, do período mais recente para o mais antigo.

    Janelas pequenas garantem que cada chunk termina (e portanto faz commit)
    bem dentro do timeout — diferente das janelas mensais, que estouravam o
    tempo e perdiam todo o trabalho da transação.
    """
    floor = date(SINCE_YEAR, 1, 1)
    cursor = min(date(BACKFILL_END_YEAR, 12, 31), date.today())
    chunks: List[Dict[str, Any]] = []
    while cursor >= floor:
        start = max(cursor - timedelta(days=CHUNK_DAYS - 1), floor)
        chunks.append(
            {
                "id": f"camara-{start.isoformat()}",
                "kind": "camara",
                "data_inicio": start.isoformat(),
                "data_fim": cursor.isoformat(),
                "year": start.year,
            }
        )
        cursor = start - timedelta(days=1)
    return chunks


def _build_chunks() -> List[Dict[str, Any]]:
    """Lista completa de chunks, intercalando Câmara e Senado para que os dois
    avancem em paralelo ao longo das execuções."""
    camara = _camara_week_chunks()
    senado = [
        # since-year embutido no id: mudar SINCE_YEAR invalida os chunks antigos
        # do Senado e força o re-backfill a partir do novo piso (ex.: 2022 -> 2018).
        # (Os chunks da Câmara já têm a data no id, então se ajustam sozinhos.)
        {"id": f"senado-{code}-since{SINCE_YEAR}", "kind": "senado", "code": code}
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
        # Sem --force-full: proposições inéditas já trazem detalhes+autores na
        # primeira passada; reprocessar as existentes seria lento e inútil num
        # backfill, e ainda torna re-execuções de um chunk rápidas (pula o que
        # já está salvo).
        return [
            sys.executable, "-m", "mamute_scrappers.camara_crawler.proposition",
            "--year", str(chunk["year"]),
            "--data-inicio", chunk["data_inicio"],
            "--data-fim", chunk["data_fim"],
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
    # Surfaça a linha de resumo do crawler, se houver, pra dar visibilidade.
    summary = next(
        (ln for ln in reversed((result.stdout or "").splitlines())
         if "concluíd" in ln.lower() or "sucesso" in ln.lower()),
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

    # Trava: se outro backfill ainda está rodando, sai sem fazer nada. Evita
    # dois processos batendo na mesma API ao mesmo tempo.
    lock_fd = _acquire_lock()
    if lock_fd is None:
        logger.info("Outro backfill já está em execução; saindo sem fazer nada.")
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
