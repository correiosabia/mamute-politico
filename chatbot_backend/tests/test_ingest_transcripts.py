"""Testes da carga inicial do índice vetorial.

A carga cobre ~122 mil discursos. A versão anterior chamava `add_documents` uma
vez por discurso (uma requisição HTTP de embeddings por linha) e não guardava
progresso: qualquer queda no meio recomeçava do zero. Ambos os pontos são
inviáveis num job que roda por horas.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from chatbot_backend.app.services.ingestion import create_splitter
from chatbot_backend.scripts import ingest_transcripts as ingest


def _row(row_id: int, **overrides) -> dict:
    row = {
        "id": row_id,
        "date": "2026-03-10",
        "summary": f"Resumo {row_id}",
        "speech_text": f"Discurso número {row_id} sobre política monetária.",
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
    """Registra cada chamada para permitir asserções sobre o lote."""

    def __init__(self) -> None:
        self.calls: list[list] = []

    def add_documents(self, documents, ids=None):  # noqa: ANN001
        self.calls.append(list(documents))


class TestDocumentosPorLote:
    def test_agrega_documentos_de_todas_as_linhas(self) -> None:
        rows = [_row(1), _row(2), _row(3)]

        documents = ingest.documents_for_rows(rows, create_splitter())

        conteudo = "\n".join(document.page_content for document in documents)
        assert "Discurso número 1" in conteudo
        assert "Discurso número 2" in conteudo
        assert "Discurso número 3" in conteudo

    def test_descarta_linhas_sem_texto(self) -> None:
        rows = [_row(1), _row(2, summary="", speech_text=""), _row(3)]

        documents = ingest.documents_for_rows(rows, create_splitter())

        conteudo = "\n".join(document.page_content for document in documents)
        assert "Discurso número 2" not in conteudo


class TestSQLDePaginacao:
    """O primeiro lote manda `after_id = NULL`.

    Sem cast explícito o Postgres não consegue inferir o tipo do parâmetro e
    recusa a consulta inteira com `AmbiguousParameter: could not determine data
    type of parameter $1` — a carga nem começava.
    """

    def test_after_id_continua_sendo_um_bind_param(self) -> None:
        """Asserção que pega o cast escrito na sintaxe errada.

        O SQLAlchemy ignora `:param` seguido de `::` — o lookahead do parser
        existe justamente para não quebrar casts de Postgres. Com
        `:after_id::bigint` o `:after_id` literal chega ao banco e vira
        `SyntaxError`. Só `CAST(:after_id AS bigint)` mantém o bind.
        """

        stmt = text(ingest.build_fetch_batch_sql())

        assert "after_id" in stmt._bindparams

    def test_after_id_tem_tipo_declarado(self) -> None:
        sql = ingest.build_fetch_batch_sql()

        assert "CAST(:after_id AS bigint)" in sql
        assert ":after_id IS NULL" not in sql
        assert ":after_id::" not in sql

    def test_pagina_por_keyset_e_nao_por_offset(self) -> None:
        sql = ingest.build_fetch_batch_sql()

        assert "st.id >" in sql
        assert "OFFSET" not in sql.upper()

    def test_ordena_por_id_para_o_keyset_ser_estavel(self) -> None:
        assert "ORDER BY st.id ASC" in ingest.build_fetch_batch_sql()


class TestCheckpoint:
    def test_grava_e_recupera_o_ultimo_id(self, tmp_path: Path) -> None:
        caminho = tmp_path / "ingest.checkpoint"

        ingest.write_checkpoint(caminho, 4242)

        assert ingest.read_checkpoint(caminho) == 4242

    def test_arquivo_inexistente_comeca_do_zero(self, tmp_path: Path) -> None:
        assert ingest.read_checkpoint(tmp_path / "nao-existe") is None

    def test_arquivo_corrompido_comeca_do_zero(self, tmp_path: Path) -> None:
        caminho = tmp_path / "ingest.checkpoint"
        caminho.write_text("lixo", encoding="utf-8")

        assert ingest.read_checkpoint(caminho) is None


class TestIdempotenciaDoLote:
    """`add_embeddings` do LangChain é INSERT puro (`bulk_save_objects`).

    Como `custom_id` é UNIQUE, reprocessar um lote já gravado estoura
    IntegrityError. A janela existe de verdade: se o processo cair entre o commit
    do lote e a escrita do checkpoint, a retomada refaz esse lote. Numa carga de
    ~600 lotes isso não é hipótese remota.
    """

    def test_remove_os_chunks_do_lote_antes_de_inserir(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        removidos: list[list[str]] = []
        monkeypatch.setattr(ingest, "get_vector_store", lambda: FakeVectorStore())
        monkeypatch.setattr(
            ingest,
            "_fetch_batch",
            lambda after_id, limit: [_row(1)] if after_id is None else [],
        )
        monkeypatch.setattr(
            ingest, "delete_chunks_by_ids", lambda ids: removidos.append(list(ids))
        )

        ingest.run(batch_size=200, checkpoint_path=tmp_path / "ck", resume=False)

        assert removidos == [["speeches_transcripts:1:0"]]

    def test_remove_antes_de_inserir_e_nao_depois(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        eventos: list[str] = []

        class Store(FakeVectorStore):
            def add_documents(self, documents, ids=None):  # noqa: ANN001
                eventos.append("add")

        monkeypatch.setattr(ingest, "get_vector_store", Store)
        monkeypatch.setattr(
            ingest,
            "_fetch_batch",
            lambda after_id, limit: [_row(1)] if after_id is None else [],
        )
        monkeypatch.setattr(
            ingest, "delete_chunks_by_ids", lambda ids: eventos.append("delete")
        )

        ingest.run(batch_size=200, checkpoint_path=tmp_path / "ck", resume=False)

        assert eventos == ["delete", "add"]


class TestExecucao:
    @pytest.fixture(autouse=True)
    def _sem_banco_vetorial(self, monkeypatch):
        """Neutraliza a limpeza do lote; ela tem cobertura própria acima."""

        monkeypatch.setattr(ingest, "delete_chunks_by_ids", lambda ids: None)

    def test_envia_um_lote_unico_e_nao_uma_chamada_por_discurso(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        store = FakeVectorStore()
        rows = [_row(1), _row(2), _row(3)]
        monkeypatch.setattr(ingest, "get_vector_store", lambda: store)
        monkeypatch.setattr(
            ingest,
            "_fetch_batch",
            lambda after_id, limit: rows if after_id is None else [],
        )

        ingest.run(batch_size=200, checkpoint_path=tmp_path / "ck", resume=False)

        assert len(store.calls) == 1, "3 discursos devem virar 1 chamada de embeddings"
        assert len(store.calls[0]) == 3

    def test_grava_checkpoint_com_o_ultimo_id_do_lote(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        caminho = tmp_path / "ck"
        monkeypatch.setattr(ingest, "get_vector_store", lambda: FakeVectorStore())
        monkeypatch.setattr(
            ingest,
            "_fetch_batch",
            lambda after_id, limit: [_row(7), _row(9)] if after_id is None else [],
        )

        ingest.run(batch_size=200, checkpoint_path=caminho, resume=False)

        assert ingest.read_checkpoint(caminho) == 9

    def test_resume_retoma_do_checkpoint_gravado(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        caminho = tmp_path / "ck"
        ingest.write_checkpoint(caminho, 100)
        vistos: list[int | None] = []

        def fake_fetch(after_id, limit):  # noqa: ANN001
            vistos.append(after_id)
            return []

        monkeypatch.setattr(ingest, "get_vector_store", lambda: FakeVectorStore())
        monkeypatch.setattr(ingest, "_fetch_batch", fake_fetch)

        ingest.run(batch_size=200, checkpoint_path=caminho, resume=True)

        assert vistos[0] == 100, "deve pedir só o que vem depois do último id gravado"

    def test_sem_resume_ignora_checkpoint_anterior(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        caminho = tmp_path / "ck"
        ingest.write_checkpoint(caminho, 100)
        vistos: list[int | None] = []

        def fake_fetch(after_id, limit):  # noqa: ANN001
            vistos.append(after_id)
            return []

        monkeypatch.setattr(ingest, "get_vector_store", lambda: FakeVectorStore())
        monkeypatch.setattr(ingest, "_fetch_batch", fake_fetch)

        ingest.run(batch_size=200, checkpoint_path=caminho, resume=False)

        assert vistos[0] is None

    def test_percorre_todas_as_paginas_ate_esgotar(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        store = FakeVectorStore()
        paginas = {None: [_row(1), _row(2)], 2: [_row(3)], 3: []}
        monkeypatch.setattr(ingest, "get_vector_store", lambda: store)
        monkeypatch.setattr(
            ingest, "_fetch_batch", lambda after_id, limit: paginas[after_id]
        )

        ingest.run(batch_size=2, checkpoint_path=tmp_path / "ck", resume=False)

        assert len(store.calls) == 2
        assert ingest.read_checkpoint(tmp_path / "ck") == 3
