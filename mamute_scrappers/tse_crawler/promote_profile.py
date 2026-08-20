"""Promove o perfil demografico ja gravado no JSONB `details` para as colunas.

Roda UMA vez apos a migration do CS-63 (e e inofensivo repetir): os ~20 mil
candidatos de 2026 ja tem o detalhe completo da DivulgaCandContas no banco, e
o fingerprint impede que o crawler refaça o detalhe so para preencher as
colunas novas — dai a promocao local, sem nenhum request ao TSE.

Nao toca linha com profile_source ja preenchido: re-execucao e barata e nao
desfaz carga posterior.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mamute_scrappers.tse_crawler.candidacy import _load_env_file  # noqa: E402
from mamute_scrappers.tse_crawler.profile import (  # noqa: E402
    PROFILE_FIELDS,
    extract_profile_from_detail,
)

logger = logging.getLogger(__name__)

COMMIT_EVERY = 1000


def run(*, persist: bool = True) -> None:
    _load_env_file()
    from mamute_scrappers.db import session_scope
    from mamute_scrappers.db.models import Candidacy

    promoted = 0
    skipped = 0
    with session_scope() as session:
        # Paginacao por keyset em lotes, com commit por lote. NADA de
        # yield_per aqui: commit no meio mata o named cursor (gotcha do
        # CS-54, PR #166). O detalhe JSONB e grande; expunge libera memoria.
        last_id = 0
        while True:
            batch = (
                session.query(Candidacy)
                .filter(Candidacy.details.isnot(None))
                .filter(Candidacy.profile_source.is_(None))
                .filter(Candidacy.id > last_id)
                .order_by(Candidacy.id)
                .limit(COMMIT_EVERY)
                .all()
            )
            if not batch:
                break
            for record in batch:
                profile = extract_profile_from_detail(record.details)
                if all(profile.get(field) is None for field in PROFILE_FIELDS):
                    skipped += 1
                    continue
                for field, value in profile.items():
                    setattr(record, field, value)
                promoted += 1
            last_id = batch[-1].id
            if persist:
                session.commit()
                logger.info("%s promovidos...", promoted)
            session.expunge_all()
        if not persist:
            session.rollback()

    logger.info(
        "Promocao concluida: %s promovidos, %s sem perfil no detalhe.%s",
        promoted,
        skipped,
        "" if persist else " (dry-run: rollback)",
    )


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="Promove perfil demografico do JSONB details para as colunas."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Nao persiste; apenas reporta."
    )
    args = parser.parse_args()
    run(persist=not args.dry_run)
