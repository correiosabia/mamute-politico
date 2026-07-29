"""Testes da construção de documentos indexados no vetor.

Contexto: o bug relatado em produção (CS-29) era o chatbot responder "não
encontrei informações sobre o parlamentar X" mesmo com discursos dele no banco.
Além do índice vazio, o texto indexado não continha o nome de quem discursou —
só o metadado. Como cada chunk é recuperado isoladamente, um chunk sem o nome
é um chunk que a busca semântica não consegue associar ao parlamentar.
"""

from __future__ import annotations

from chatbot_backend.app.services.ingestion import build_documents, create_splitter


def _row(**overrides) -> dict:
    row = {
        "id": 4242,
        "date": "2026-03-10",
        "summary": "Debate sobre juros bancários.",
        "speech_text": "Falo hoje sobre o papel do banco central na economia.",
        "session_number": "12",
        "type": "DISCURSO",
        "parliamentarian_id": 544,
        "parliamentarian_name": "Flávio Bolsonaro",
        "parliamentarian_party": "pl",
        "parliamentarian_state": "rj",
        "parliamentarian_role": "senador",
    }
    row.update(overrides)
    return row


def test_chunk_identifica_o_parlamentar_no_texto_indexado() -> None:
    documents = build_documents(_row(), create_splitter())

    assert documents
    assert "Flávio Bolsonaro" in documents[0].page_content


def test_todos_os_chunks_identificam_o_parlamentar() -> None:
    """Cada chunk é recuperado sozinho: todos precisam dizer quem falou."""

    longo = "O banco central precisa de autonomia. " * 400
    documents = build_documents(_row(speech_text=longo), create_splitter())

    assert len(documents) > 1, "cenário exige múltiplos chunks para ter valor"
    for document in documents:
        assert "Flávio Bolsonaro" in document.page_content


def test_cabecalho_traz_partido_e_uf() -> None:
    documents = build_documents(_row(), create_splitter())

    header = documents[0].page_content
    assert "PL" in header
    assert "RJ" in header


def test_conteudo_do_discurso_permanece_no_chunk() -> None:
    documents = build_documents(_row(), create_splitter())

    todo_texto = "\n".join(document.page_content for document in documents)
    assert "papel do banco central na economia" in todo_texto
    assert "Debate sobre juros bancários." in todo_texto


def test_parlamentar_desconhecido_nao_quebra_a_indexacao() -> None:
    documents = build_documents(
        _row(
            parliamentarian_name=None,
            parliamentarian_party=None,
            parliamentarian_state=None,
        ),
        create_splitter(),
    )

    assert documents
    assert "papel do banco central" in documents[0].page_content


def test_discurso_sem_texto_continua_sendo_descartado() -> None:
    documents = build_documents(
        _row(summary="", speech_text=""),
        create_splitter(),
    )

    assert documents == []
