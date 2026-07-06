"""CLI: python -m mamute_scrappers.scripts.notificacao --periodicidade week"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mamute_scrappers.scripts.notificacao.config import (  # noqa: E402
    PERIODICIDADES_VALIDAS,
    default_highlight_limit,
)
from mamute_scrappers.scripts.notificacao.runner import run  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Envia relatórios por e-mail aos projetos do Mamute Político.",
    )
    parser.add_argument(
        "--periodicidade",
        choices=sorted(PERIODICIDADES_VALIDAS),
        default="week",
        help=(
            "Periodicidade: day/week/fortnight/month filtram pelo "
            "tier.periodicidade_email; total é modo teste (todos os projetos, "
            "até 10 destaques)."
        ),
    )
    parser.add_argument(
        "--projeto-id",
        type=int,
        default=None,
        help="Envia apenas para um projeto (ignora filtro de tier).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Monta relatórios e grava HTML em output/, sem enviar e-mail.",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Lista id, e-mail e nome dos destinatários (TSV) e encerra.",
    )
    parser.add_argument(
        "--include-without-tier",
        action="store_true",
        help="Inclui projetos sem tier ao listar destinatários.",
    )
    parser.add_argument(
        "--send-if-empty",
        action="store_true",
        help="Envia mesmo sem atividade no período.",
    )
    parser.add_argument(
        "--highlight-limit",
        type=int,
        default=None,
        help=(
            "Máximo de destaques no corpo (padrão: 9 para day/week/month, 10 para total)."
        ),
    )
    parser.add_argument(
        "--save-html",
        action="store_true",
        help="Grava HTML em mamute_scrappers/scripts/notificacao/output/ mesmo sem dry-run.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=None,
        help="Threads paralelas (padrão: número de CPUs).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Log em nível DEBUG.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    highlight_limit = args.highlight_limit
    if highlight_limit is None:
        highlight_limit = default_highlight_limit(args.periodicidade)

    try:
        results = run(
            args.periodicidade,
            dry_run=args.dry_run,
            projeto_id=args.projeto_id,
            highlight_limit=highlight_limit,
            skip_empty=not args.send_if_empty,
            include_without_tier=args.include_without_tier,
            max_workers=args.max_workers,
            list_only=args.list_only,
            save_html=args.save_html or args.dry_run,
        )
    except Exception as exc:
        logging.error("%s", exc)
        return 1

    sent = sum(1 for line in results if "enviado" in line or "dry-run" in line)
    logging.info("Concluído: %s linha(s) de resultado, %s processado(s).", len(results), sent)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
