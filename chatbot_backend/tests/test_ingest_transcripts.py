"""Testes da carga inicial do índice vetorial.

A carga cobre ~122 mil discursos. A versão anterior chamava `add_documents` uma
vez por discurso (uma requisição HTTP de embeddings por linha) e não guardava
progresso: qualquer queda no meio recomeçava do zero. Ambos os pontos são
inviáveis num job que roda por horas.
"""

from __future__ import annotations

from pathlib import Path

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


class TestExecucao:
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
