"""Script utilitário para indexar notas taquigráficas no pgvector.

A carga inicial cobre ~122 mil discursos, então dois cuidados são obrigatórios:

* **Lote único de embeddings por página.** Uma chamada por discurso significaria
  ~122 mil requisições HTTP e um job de muitas horas. Os documentos de toda a
  página são embarcados numa chamada só.
* **Retomada.** O progresso é gravado em disco a cada página. Uma queda no meio
  da carga retoma de onde parou em vez de recomeçar do zero.

A paginação é por *keyset* (`id > último`), não por OFFSET: o custo por página
fica constante em vez de crescer conforme a carga avança.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, Optional, Sequence

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import text

from chatbot_backend.app.core.database import get_session
from chatbot_backend.app.services.ingestion import build_documents, create_splitter
from chatbot_backend.app.services.vector_store import get_vector_store

DEFAULT_CHECKPOINT = Path("ingest_transcripts.checkpoint")


def read_checkpoint(path: Path) -> Optional[int]:
    """Último `id` confirmado, ou None para começar do início."""

    try:
        return int(Path(path).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def write_checkpoint(path: Path, last_id: int) -> None:
    """Persiste o progresso da carga."""

    Path(path).write_text(str(last_id), encoding="utf-8")


def documents_for_rows(
    rows: Sequence[dict],
    splitter: RecursiveCharacterTextSplitter,
) -> list[Document]:
    """Achata os chunks de várias linhas num único lote."""

    documents: list[Document] = []
    for row in rows:
        documents.extend(build_documents(row, splitter))
    return documents


def _fetch_batch(after_id: Optional[int], limit: int) -> list[dict]:
    query = text(
        """
        SELECT
            st.id,
            st.date,
            st.summary,
            st.speech_text,
            st.session_number,
            st.type,
            st.parliamentarian_id,
            p.name AS parliamentarian_name,
            p.party AS parliamentarian_party,
            p.state_elected AS parliamentarian_state,
            p.type AS parliamentarian_role
        FROM speeches_transcripts st
        LEFT JOIN parliamentarian p ON p.id = st.parliamentarian_id
        WHERE (:after_id IS NULL OR st.id > :after_id)
        ORDER BY st.id ASC
        LIMIT :limit
        """
    )
    with get_session() as session:
        rows = session.execute(
            query, {"after_id": after_id, "limit": limit}
        ).mappings()
        return [dict(row) for row in rows]


def run(
    batch_size: int,
    checkpoint_path: Path = DEFAULT_CHECKPOINT,
    resume: bool = True,
    max_batches: Optional[int] = None,
) -> None:
    splitter = create_splitter()
    vector_store = get_vector_store()

    after_id = read_checkpoint(checkpoint_path) if resume else None
    if after_id is not None:
        print(f"[info] Retomando a partir do discurso {after_id}.")

    processed_rows = 0
    processed_chunks = 0
    batch_index = 0

    while max_batches is None or batch_index < max_batches:
        rows = _fetch_batch(after_id, batch_size)
        if not rows:
            break

        documents = documents_for_rows(rows, splitter)
        if documents:
            chunk_ids = [
                doc.metadata.get("chunk_id")
                for doc in documents
                if doc.metadata and isinstance(doc.metadata.get("chunk_id"), str)
            ]
            vector_store.add_documents(documents, ids=chunk_ids)
            processed_chunks += len(documents)

        after_id = rows[-1]["id"]
        processed_rows += len(rows)
        batch_index += 1
        write_checkpoint(checkpoint_path, after_id)

        print(
            f"Lote {batch_index}: {len(rows)} discurso(s) -> "
            f"{len(documents)} chunk(s) | último id={after_id} | "
            f"acumulado: {processed_rows} discurso(s), {processed_chunks} chunk(s)"
        )

    print(
        "Processo concluído. "
        f"{processed_rows} discurso(s) e {processed_chunks} chunk(s) indexados."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Indexa notas taquigráficas no vetor PGVector."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="Quantidade de discursos carregados por rodada (default=200).",
    )
    parser.add_argument(
        "--max-batches",
        type=int,
        default=None,
        help="Limita o total de lotes processados (default=todo).",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=DEFAULT_CHECKPOINT,
        help=(
            "Arquivo onde o progresso é gravado "
            f"(default={DEFAULT_CHECKPOINT})."
        ),
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignora o checkpoint anterior e recomeça a carga do início.",
    )

    args = parser.parse_args()
    run(
        batch_size=args.batch_size,
        checkpoint_path=args.checkpoint,
        resume=not args.no_resume,
        max_batches=args.max_batches,
    )


if __name__ == "__main__":
    main()
