"""Carga de candidaturas historicas dos CSVs de dados abertos do TSE — CS-63.

Um ZIP por ano (consulta_cand_{ano}.zip, ~3-5 MB), um CSV por UF dentro dele,
latin-1, separador ';'. O TSE regerou TODOS os anos com o cabecalho moderno
(conferido em 2026-08-20: ate 1998 tem header nomeado), entao a leitura e por
nome de coluna — sem layout posicional.

Gotchas da fonte, medidos ao vivo:
- O CDN (Akamai) recusa requests sem o conjunto COMPLETO de headers de
  navegador — User-Agent sozinho toma 403; Accept-Encoding e os Sec-Fetch-*
  fazem parte do passe.
- Sentinelas #NE/#NE#/#NULO/#NULO# viram None (cor/raca so existe desde 2014,
  federacao desde 2022).
- Candidato de 2o turno aparece em DUAS linhas (NR_TURNO 1 e 2); fica a do
  turno maior, que carrega a situacao final (ELEITO/NAO ELEITO).
- SQ_CANDIDATO e o mesmo id da DivulgaCandContas (conferido 5/5 contra a base
  de 2026), entao a chave natural (election_year, tse_candidate_id) casa as
  duas fontes.

Regra de convivencia com a API: linha nova ou ja vinda de CSV e sobrescrita
inteira; linha da DivulgaCandContas (2026) so tem NULL completado — o detalhe
da API e mais fresco e nunca perde para carga em lote.
"""

from __future__ import annotations

import csv
import io
import logging
import sys
import tempfile
import zipfile
from collections import Counter
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Tuple

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mamute_scrappers.tse_crawler.candidacy import (  # noqa: E402
    _load_env_file,
    _load_parliamentarian_index,
)
from mamute_scrappers.tse_crawler.matching import (  # noqa: E402
    MATCH_STATUS_MANUAL,
    match_candidacy,
)
from mamute_scrappers.tse_crawler.parsing import (  # noqa: E402
    coerce_text,
    normalize_cpf,
    parse_int,
)
from mamute_scrappers.tse_crawler.profile import (  # noqa: E402
    PROFILE_SOURCE_API,
    PROFILE_SOURCE_CSV,
    extract_profile_from_csv_row,
    normalize_profile_text,
)

logger = logging.getLogger(__name__)

ZIP_URL = (
    "https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/"
    "consulta_cand_{year}.zip"
)

# Eleicoes gerais (federais + estaduais) na janela do CS-63. 2026 fica de
# fora de proposito: a fonte viva dela e a DivulgaCandContas (candidacy.py).
GENERAL_YEARS = (1994, 1998, 2002, 2006, 2010, 2014, 2018, 2022)

# O Akamai do TSE exige o conjunto completo; subconjuntos tomam 403.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "sec-ch-ua": '"Google Chrome";v="126", "Chromium";v="126", "Not-A.Brand";v="8"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
}

REQUEST_TIMEOUT = 300
COMMIT_EVERY = 500

Candidacy: Any = None

# Tudo que a carga CSV sabe preencher. Em linha da API (profile_source =
# 'divulgacand') estes campos so sao completados quando NULL.
_CSV_FIELDS = (
    "office_code",
    "office",
    "state",
    "ballot_number",
    "ballot_name",
    "full_name",
    "party",
    "coalition",
    "status",
    "totalization_status",
    "cpf",
    "voter_id",
    "birth_date",
    "gender",
    "race",
    "education",
    "occupation",
    "marital_status",
    "nationality",
    "federation",
)


def _ensure_model() -> None:
    global Candidacy
    if Candidacy is None:
        from mamute_scrappers.db.models import Candidacy as CandidacyRuntime

        Candidacy = CandidacyRuntime


def download_zip(year: int, cache_dir: Path) -> Path:
    """Baixa (ou reusa) o ZIP anual. Cache por arquivo: re-execucao e gratis."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"consulta_cand_{year}.zip"
    if target.exists() and zipfile.is_zipfile(target):
        logger.info("Usando ZIP em cache: %s", target)
        return target

    url = ZIP_URL.format(year=year)
    logger.info("Baixando %s", url)
    response = requests.get(
        url, headers=BROWSER_HEADERS, timeout=REQUEST_TIMEOUT, stream=True
    )
    response.raise_for_status()
    tmp = target.with_suffix(".part")
    with open(tmp, "wb") as handle:
        for chunk in response.iter_content(chunk_size=1 << 20):
            handle.write(chunk)
    if not zipfile.is_zipfile(tmp):
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Resposta de {url} nao e um ZIP (bloqueio do CDN?).")
    tmp.rename(target)
    return target


def iter_csv_rows(zip_path: Path) -> Iterator[Dict[str, str]]:
    with zipfile.ZipFile(zip_path) as archive:
        for name in sorted(archive.namelist()):
            if not name.lower().endswith(".csv"):
                continue
            with archive.open(name) as handle:
                reader = csv.DictReader(
                    io.TextIOWrapper(handle, encoding="latin-1"), delimiter=";"
                )
                yield from reader


def build_csv_payload(row: Dict[str, str], *, year: int) -> Optional[Dict[str, Any]]:
    """Payload de upsert a partir de uma linha do consulta_cand."""
    tse_candidate_id = parse_int(row.get("SQ_CANDIDATO"))
    if tse_candidate_id is None:
        return None

    payload: Dict[str, Any] = {
        "election_year": year,
        "tse_candidate_id": tse_candidate_id,
        "turno": parse_int(row.get("NR_TURNO")) or 1,
        "office_code": parse_int(row.get("CD_CARGO")),
        "office": normalize_profile_text(row.get("DS_CARGO")),
        "state": coerce_text(row.get("SG_UF")),
        "ballot_number": parse_int(row.get("NR_CANDIDATO")),
        "ballot_name": coerce_text(row.get("NM_URNA_CANDIDATO")),
        "full_name": coerce_text(row.get("NM_CANDIDATO")),
        "party": coerce_text(row.get("SG_PARTIDO")),
        "coalition": normalize_profile_text(row.get("NM_COLIGACAO")),
        "status": normalize_profile_text(row.get("DS_SITUACAO_CANDIDATURA")),
        "totalization_status": normalize_profile_text(row.get("DS_SIT_TOT_TURNO")),
        "cpf": normalize_cpf(row.get("NR_CPF_CANDIDATO")),
        "voter_id": coerce_text(row.get("NR_TITULO_ELEITORAL_CANDIDATO")),
    }
    payload.update(extract_profile_from_csv_row(row))
    return payload


def dedupe_second_round(
    payloads: "Iterator[Dict[str, Any]] | list",
) -> Dict[Tuple[Optional[str], int], Dict[str, Any]]:
    """Uma candidatura por (UF, SQ_CANDIDATO); prevalece o turno maior.

    A UF na chave e obrigatoria: em 2002/2006 o SQ_CANDIDATO repete entre
    UFs (sequencial por estado). Os arquivos desses anos tambem trazem cada
    linha de 1o turno duplicada em dobro — o dedupe absorve as duas coisas.
    """
    by_key: Dict[Tuple[Optional[str], int], Dict[str, Any]] = {}
    for payload in payloads:
        key = (payload.get("state"), payload["tse_candidate_id"])
        current = by_key.get(key)
        if current is None or payload["turno"] > current["turno"]:
            by_key[key] = payload
    return by_key


def upsert_csv_candidacy(session: Any, payload: Dict[str, Any]) -> Tuple[Any, bool]:
    """Grava uma linha do CSV respeitando o que veio da DivulgaCandContas."""
    _ensure_model()

    # A UF entra no filtro por causa de 2002/2006 (SQ_CANDIDATO por UF); ver
    # a constraint uq_candidacy_election_state_tse_id.
    record = (
        session.query(Candidacy)
        .filter(
            Candidacy.election_year == payload["election_year"],
            Candidacy.state == payload["state"],
            Candidacy.tse_candidate_id == payload["tse_candidate_id"],
        )
        .one_or_none()
    )

    created = False
    if record is None:
        record = Candidacy(
            election_year=payload["election_year"],
            state=payload["state"],
            tse_candidate_id=payload["tse_candidate_id"],
        )
        session.add(record)
        created = True

    api_owned = (not created) and record.profile_source == PROFILE_SOURCE_API
    for field in _CSV_FIELDS:
        if api_owned and getattr(record, field) is not None:
            continue
        setattr(record, field, payload.get(field))

    if not api_owned:
        record.profile_source = PROFILE_SOURCE_CSV
        if record.match_status != MATCH_STATUS_MANUAL:
            record.parliamentarian_id = payload.get("parliamentarian_id")
            record.match_status = payload.get("match_status")

    if created:
        session.flush()

    return record, created


def run(
    *,
    years: Tuple[int, ...] = GENERAL_YEARS,
    persist: bool = True,
    dry_run_limit: Optional[int] = None,
    cache_dir: Optional[Path] = None,
) -> None:
    _load_env_file()
    cache_dir = cache_dir or Path(tempfile.gettempdir()) / "tse_consulta_cand"
    index = _load_parliamentarian_index()

    if persist:
        _ensure_model()
        from mamute_scrappers.db import session_scope

        session_context = session_scope()
    else:
        session_context = nullcontext(None)

    with session_context as session:
        for year in years:
            zip_path = download_zip(year, cache_dir)

            skipped = 0

            def _payloads() -> Iterator[Dict[str, Any]]:
                nonlocal skipped
                for row in iter_csv_rows(zip_path):
                    payload = build_csv_payload(row, year=year)
                    if payload is None:
                        skipped += 1
                        continue
                    yield payload

            by_id = dedupe_second_round(_payloads())

            status_counter: Counter = Counter()
            inserted = 0
            updated = 0
            processed = 0
            for payload in by_id.values():
                payload.pop("turno", None)
                result = match_candidacy(
                    cpf=payload.get("cpf"),
                    full_name=payload.get("full_name"),
                    ballot_name=payload.get("ballot_name"),
                    state=payload.get("state"),
                    index=index,
                )
                payload["parliamentarian_id"] = result.parliamentarian_id
                payload["match_status"] = result.status
                status_counter[result.status] += 1
                processed += 1

                if session is not None:
                    _, created = upsert_csv_candidacy(session, payload)
                    if created:
                        inserted += 1
                    else:
                        updated += 1
                    # Commit parcial, como na carga da DivulgaCandContas: a
                    # carga de um ano nao pode sumir por falha no seguinte.
                    if (inserted + updated) % COMMIT_EVERY == 0:
                        session.commit()

                if dry_run_limit is not None and processed >= dry_run_limit:
                    break

            logger.info("=== consulta_cand %s ===", year)
            logger.info(
                "Candidaturas: %s (linhas ilegiveis: %s) | casamento: %s",
                len(by_id),
                skipped,
                dict(status_counter),
            )
            if persist:
                logger.info(
                    "Persistencia: %s inseridas, %s atualizadas.", inserted, updated
                )
            else:
                logger.info("Modo dry-run: nada foi gravado.")

            if dry_run_limit is not None and processed >= dry_run_limit:
                return


def _parse_years(raw: Optional[str]) -> Tuple[int, ...]:
    if not raw:
        return GENERAL_YEARS
    years = tuple(int(part) for part in raw.replace(",", " ").split())
    unknown = [y for y in years if y not in GENERAL_YEARS]
    if unknown:
        raise SystemExit(
            f"Anos fora das eleicoes gerais 1994-2022: {unknown}. "
            "2026 e alimentado pela DivulgaCandContas (candidacy.py)."
        )
    return years


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description=(
            "Carrega candidaturas historicas (dados abertos do TSE) na candidacy."
        )
    )
    parser.add_argument(
        "--anos",
        help=(
            "Anos separados por virgula/espaco (default: todas as gerais "
            "1994-2022)."
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Nao persiste; apenas reporta."
    )
    parser.add_argument(
        "--limit", type=int, help="Interrompe apos N candidaturas processadas."
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        help="Diretorio para os ZIPs baixados (default: tmp do sistema).",
    )

    args = parser.parse_args()
    run(
        years=_parse_years(args.anos),
        persist=not args.dry_run,
        dry_run_limit=args.limit,
        cache_dir=args.cache_dir,
    )
