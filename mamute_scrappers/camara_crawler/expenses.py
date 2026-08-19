"""Coleta dos gastos da cota parlamentar (CEAP) da Camara — CS-57.

Fonte: arquivo anual em massa https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip
(~70 MB de CSV, ~208 mil linhas/ano), atualizado diariamente pela Camara.

A API REST `GET /api/v2/deputados/{id}/despesas` NAO e usada: em 19/08/2026
ela devolvia x-total-count: 0 para todos os deputados e anos testados (mesmo
comportamento do teste de 12/08 registrado na CS-57). O arquivo em massa e a
fonte que funciona — e dispensa paginacao e rate limit: e 1 download por ano.

O vinculo com o parlamentar e join direto: `ideCadastro` do CSV e o mesmo id
que guardamos em parliamentarian_code para type='Deputado'. Linhas sem
ideCadastro (liderancas partidarias) sao persistidas com parliamentarian_id
nulo — fato publico nao some, so nao aparece em perfil nenhum.
"""

from __future__ import annotations

import csv
import io
import logging
import sys
import tempfile
import zipfile
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests  # noqa: E402

from mamute_scrappers.expenses.upsert import (  # noqa: E402
    COMMIT_EVERY,
    fallback_source_key,
    upsert_expense,
)

logger = logging.getLogger(__name__)

BULK_URL = "https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip"
DOWNLOAD_TIMEOUT = 300  # segundos; o zip tem ~8 MB, mas a rede do cron oscila
HOUSE = "camara"


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    cleaned = " ".join(str(value).split())
    return cleaned or None


def _decimal(value: Any) -> Optional[Decimal]:
    text = _text(value)
    if text is None:
        return None
    try:
        # A fonte usa ponto decimal ("104.58"); a troca de virgula cobre
        # eventual mudanca de formato sem quebrar o parse atual.
        return Decimal(text.replace(",", "."))
    except InvalidOperation:
        return None


def _date(value: Any) -> Optional[date]:
    text = _text(value)
    if text is None:
        return None
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _details(row: Dict[str, str]) -> Optional[str]:
    """Passageiro e trecho dos bilhetes; vazio nas demais despesas."""
    parts = []
    passageiro = _text(row.get("txtPassageiro"))
    trecho = _text(row.get("txtTrecho"))
    if passageiro:
        parts.append(f"Passageiro: {passageiro}")
    if trecho:
        parts.append(f"Trecho: {trecho}")
    return "; ".join(parts) or None


def build_payload(row: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Converte uma linha do CSV no payload de upsert_expense.

    Devolve tambem `ide_cadastro` (id do deputado nos dados abertos), que o
    laco de coleta troca por parliamentarian_id; None nas liderancas.
    """
    year = _text(row.get("numAno"))
    month = _text(row.get("numMes"))
    expense_type = _text(row.get("txtDescricao"))
    net_value = _decimal(row.get("vlrLiquido"))
    if year is None or month is None or expense_type is None or net_value is None:
        return None

    ide_documento = _text(row.get("ideDocumento"))
    sub_cota = _text(row.get("numSubCota")) or "0"
    parcela = _text(row.get("numParcela")) or "0"
    if ide_documento and ide_documento != "0":
        # Prefixo da subcota separa espacos de id distintos (SIGEPA emite ids
        # ~300 mil; a cota, ~8 milhoes — hoje nao colidem, mas nada garante).
        source_key = f"{sub_cota}:{ide_documento}:{parcela}"
    else:
        source_key = fallback_source_key(
            row.get("ideCadastro"),
            row.get("nuDeputadoId"),
            year,
            month,
            sub_cota,
            row.get("txtFornecedor"),
            row.get("txtCNPJCPF"),
            row.get("txtNumero"),
            row.get("datEmissao"),
            row.get("vlrLiquido"),
        )

    ide_cadastro = _text(row.get("ideCadastro"))

    return {
        "house": HOUSE,
        "source_key": source_key,
        "ide_cadastro": int(ide_cadastro) if ide_cadastro else None,
        "year": int(year),
        "month": int(month),
        "expense_type": expense_type,
        "supplier_name": _text(row.get("txtFornecedor")),
        "supplier_id": _text(row.get("txtCNPJCPF")),
        "document_number": _text(row.get("txtNumero")),
        "document_date": _date(row.get("datEmissao")),
        "details": _details(row),
        "document_value": _decimal(row.get("vlrDocumento")),
        "glosa_value": _decimal(row.get("vlrGlosa")),
        "net_value": net_value,
        "document_url": _text(row.get("urlDocumento")),
    }


def iter_csv_rows(path: Path) -> Iterator[Dict[str, str]]:
    """Le o CSV extraido (utf-8 com BOM, separador ';')."""
    with open(path, encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle, delimiter=";")


def download_year_csv(ano: int, dest_dir: Path) -> Path:
    """Baixa o zip anual e extrai o CSV em dest_dir."""
    url = BULK_URL.format(ano=ano)
    logger.info("Baixando %s", url)
    zip_path = dest_dir / f"Ano-{ano}.csv.zip"
    with requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT) as resp:
        resp.raise_for_status()
        with open(zip_path, "wb") as out:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                out.write(chunk)
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.endswith(".csv")]
        if not names:
            raise RuntimeError(f"Zip de {ano} sem CSV: {zf.namelist()}")
        zf.extract(names[0], dest_dir)
    return dest_dir / names[0]


def _deputy_map(session: Any) -> Dict[int, int]:
    """parliamentarian_code -> id interno, so deputados."""
    from mamute_scrappers.db.models import Parliamentarian

    rows = (
        session.query(Parliamentarian.parliamentarian_code, Parliamentarian.id)
        .filter(Parliamentarian.type == "Deputado")
        .filter(Parliamentarian.parliamentarian_code.isnot(None))
        .all()
    )
    return {int(code): pid for code, pid in rows}


def expenses(
    *,
    ano: Optional[int] = None,
    persist: bool = True,
    dry_run_limit: Optional[int] = None,
    csv_path: Optional[Path] = None,
) -> None:
    """Coleta os gastos de cota de um ano e persiste por upsert idempotente."""
    ano = ano or date.today().year

    if persist:
        from mamute_scrappers.db import session_scope

        session_context = session_scope()
    else:
        # Dry-run diagnostica a fonte sem exigir banco (nem DATABASE_URL).
        from contextlib import nullcontext

        session_context = nullcontext(None)

    total = 0
    sem_cadastro = 0
    sem_vinculo = 0
    inserted = 0
    updated = 0

    with session_context as session:
        deputies = _deputy_map(session) if session is not None else {}
        logger.info("Deputados na base: %s", len(deputies))

        with tempfile.TemporaryDirectory() as tmp:
            path = csv_path or download_year_csv(ano, Path(tmp))
            for row in iter_csv_rows(path):
                payload = build_payload(row)
                if payload is None:
                    continue
                total += 1

                ide_cadastro = payload.pop("ide_cadastro")
                if ide_cadastro is None:
                    sem_cadastro += 1
                    payload["parliamentarian_id"] = None
                else:
                    payload["parliamentarian_id"] = deputies.get(ide_cadastro)
                    if payload["parliamentarian_id"] is None:
                        # Deputado fora da base (legislatura anterior): a
                        # linha persiste sem vinculo, como decidido na spec.
                        sem_vinculo += 1

                if session is not None:
                    _, created = upsert_expense(session, payload)
                    if created:
                        inserted += 1
                    else:
                        updated += 1
                    if (inserted + updated) % COMMIT_EVERY == 0:
                        session.commit()

                if dry_run_limit is not None and total >= dry_run_limit:
                    break

    logger.info("=== Cota Camara %s ===", ano)
    logger.info("Linhas processadas: %s", total)
    logger.info("Sem ideCadastro (liderancas): %s", sem_cadastro)
    logger.info("Deputado fora da base: %s", sem_vinculo)
    if persist:
        logger.info("Persistencia: %s inseridas, %s atualizadas.", inserted, updated)
    else:
        logger.info("Modo dry-run: nada foi gravado.")


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="Coleta gastos da cota parlamentar (CEAP) da Camara."
    )
    parser.add_argument("--ano", type=int, help="Ano da coleta (default: corrente).")
    parser.add_argument("--dry-run", action="store_true", help="Nao persiste.")
    parser.add_argument("--limit", type=int, help="Para apos N linhas.")
    parser.add_argument(
        "--csv-path",
        type=Path,
        help="Usa um CSV ja baixado em vez de baixar o zip da fonte.",
    )

    args = parser.parse_args()
    expenses(
        ano=args.ano,
        persist=not args.dry_run,
        dry_run_limit=args.limit,
        csv_path=args.csv_path,
    )
