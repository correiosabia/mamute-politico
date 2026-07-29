"""Testes da sincronização incremental do índice vetorial.

`PGVector.delete()` só remove quando recebe `ids`; qualquer outro argumento cai
no `**kwargs` e é descartado sem erro. A chamada `delete(filter={"source": ...})`
que existia aqui era um no-op silencioso: discursos reindexados deixavam para
trás os chunks da versão anterior, que seguiam sendo recuperados pela busca.
"""

from __future__ import annotations

from chatbot_backend.scripts import sync_transcripts as sync


def _row(row_id: int, **overrides) -> dict:
    row = {
        "id": row_id,
        "date": "2026-03-10",
        "summary": f"Resumo {row_id}",
        "speech_text": f"Discurso {row_id} sobre política monetária.",
        "session_number": "1",
        "type": "DISCURSO",
        "parliamentarian_id": 544,
        "parliamentarian_name": "Flávio Bolsonaro",
        "parliamentarian_party": "PL",
        "parliamentarian_state": "RJ",
        "parliamentarian_role": "senador",
    }
    row.update(overrides)
    return row


class FakeVectorStore:
    def __init__(self) -> None:
        self.added: list[list] = []

    def add_documents(self, documents, ids=None):  # noqa: ANN001
        self.added.append(list(documents))


class TestRemocaoDaVersaoAnterior:
    def test_remove_os_chunks_antigos_do_discurso_reindexado(
        self, monkeypatch
    ) -> None:
        removidos: list[str] = []
        monkeypatch.setattr(sync, "get_vector_store", lambda: FakeVectorStore())
        monkeypatch.setattr(sync, "_fetch_updated_rows", lambda since, limit: [_row(42)])
        monkeypatch.setattr(
            sync, "delete_chunks_by_source", lambda source: removidos.append(source)
        )

        sync.run(window_hours=6, since=None, limit=500, dry_run=False)

        assert removidos == ["speeches_transcripts:42"]

    def test_dry_run_nao_remove_nada(self, monkeypatch) -> None:
        removidos: list[str] = []
        monkeypatch.setattr(sync, "get_vector_store", lambda: FakeVectorStore())
        monkeypatch.setattr(sync, "_fetch_updated_rows", lambda since, limit: [_row(42)])
        monkeypatch.setattr(
            sync, "delete_chunks_by_source", lambda source: removidos.append(source)
        )

        sync.run(window_hours=6, since=None, limit=500, dry_run=True)

        assert removidos == []

    def test_remove_antes_de_reinserir(self, monkeypatch) -> None:
        """Inverter a ordem apagaria os chunks recém-gravados."""

        eventos: list[str] = []

        class Store(FakeVectorStore):
            def add_documents(self, documents, ids=None):  # noqa: ANN001
                eventos.append("add")

        monkeypatch.setattr(sync, "get_vector_store", Store)
        monkeypatch.setattr(sync, "_fetch_updated_rows", lambda since, limit: [_row(42)])
        monkeypatch.setattr(
            sync, "delete_chunks_by_source", lambda source: eventos.append("delete")
        )

        sync.run(window_hours=6, since=None, limit=500, dry_run=False)

        assert eventos == ["delete", "add"]


class TestSQLDeRemocao:
    def test_filtra_por_source_e_pela_colecao(self) -> None:
        statement = sync.build_delete_by_source_sql()

        assert "DELETE FROM langchain_pg_embedding" in statement
        assert "cmetadata->>'source' = :source" in statement
        assert "langchain_pg_collection" in statement
