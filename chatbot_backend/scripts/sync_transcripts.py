"""Sincroniza periodicamente as notas taquigráficas com o índice vetorial."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import text

from chatbot_backend.app.core.config import get_settings
from chatbot_backend.app.core.database import get_session
from chatbot_backend.app.services.ingestion import build_documents, create_splitter
from chatbot_backend.app.services.vector_store import get_vector_engine, get_vector_store


def build_delete_by_source_sql() -> str:
    """DELETE dos chunks de um discurso, restrito à coleção configurada.

    `PGVector.delete()` só remove por `ids` — argumentos como `filter` são
    engolidos pelo `**kwargs` sem erro nenhum. Como a quantidade de chunks de um
    discurso muda quando o texto é editado, apagar por id deixaria sobras; o
    filtro por `source` remove a versão anterior inteira.
    """

    return (
        "DELETE FROM langchain_pg_embedding "
        "WHERE cmetadata->>'source' = :source "
        "AND collection_id = ("
        "SELECT uuid FROM langchain_pg_collection WHERE name = :collection"
        ")"
    )


def delete_chunks_by_source(source: str) -> None:
    """Remove do índice todos os chunks de um discurso."""

    settings = get_settings()
    with get_vector_engine().begin() as conn:
        conn.execute(
            text(build_delete_by_source_sql()),
            {
                "source": source,
                "collection": settings.pgvector_collection_name,
            },
        )


def _parse_since(window_hours: float, since: str | None) -> datetime:
    if since:
        try:
            parsed = datetime.fromisoformat(since)
        except ValueError as exc:  # pragma: no cover - validação CLI
            raise SystemExit(f"Formato inválido para --since: {since}") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    return datetime.now(timezone.utc) - timedelta(hours=window_hours)


def _fetch_updated_rows(
    since: datetime,
    limit: int,
) -> Iterable[dict]:
    query = text(
        """
        SELECT
            st.id,
            st.date,
            st.summary,
            st.speech_text,
            st.session_number,
            st.type,
            st.updated_at,
            st.parliamentarian_id,
            p.name AS parliamentarian_name,
            p.party AS parliamentarian_party,
            p.state_elected AS parliamentarian_state,
            p.type AS parliamentarian_role
        FROM speeches_transcripts st
        LEFT JOIN parliamentarian p ON p.id = st.parliamentarian_id
        WHERE st.updated_at >= :since
        ORDER BY st.updated_at ASC, st.id ASC
        LIMIT :limit
        """
    )
    with get_session() as session:
        rows = session.execute(
            query, {"since": since, "limit": limit}
        ).mappings()
        for row in rows:
            yield dict(row)


def run(window_hours: float, since: str | None, limit: int, dry_run: bool) -> None:
    cutoff = _parse_since(window_hours, since)
    splitter = create_splitter()
    vector_store = get_vector_store()

    processed_rows = 0
    processed_chunks = 0

    for row in _fetch_updated_rows(cutoff, limit):
        documents = build_documents(row, splitter)
        if not documents:
            continue

        source = documents[0].metadata.get("source") if documents[0].metadata else None
        chunk_ids = [
            doc.metadata.get("chunk_id") for doc in documents if doc.metadata
        ]

        if not dry_run:
            # A remoção precisa vir antes da reinserção: invertida, apagaria os
            # chunks recém-gravados.
            if source:
                delete_chunks_by_source(source)
            vector_store.add_documents(
                documents,
                ids=[chunk_id for chunk_id in chunk_ids if isinstance(chunk_id, str)],
            )

        processed_rows += 1
        processed_chunks += len(documents)
        print(
            f"Sincronizado discurso {row.get('id')} -> {len(documents)} chunk(s)"
        )

    print(
        "Resumo: "
        f"{processed_rows} discurso(s) processados, {processed_chunks} chunk(s) "
        "atualizados. "
        f"Janela considerada desde {cutoff.isoformat()}."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Atualiza o índice vetorial apenas com notas taquigráficas novas ou "
            "alteradas."
        )
    )
    parser.add_argument(
        "--window-hours",
        type=float,
        default=6.0,
        help="Janela retroativa em horas usada quando --since não é informado (default=6).",
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="Timestamp ISO-8601 que define o ponto de corte (precede window-hours).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Número máximo de discursos carregados por execução (default=500).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Executa a busca sem gravar dados no índice vetorial.",
    )

    args = parser.parse_args()

    run(
        window_hours=args.window_hours,
        since=args.since,
        limit=args.limit,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
