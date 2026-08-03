"""Documentos que citam o tema literal vêm antes dos apenas semanticamente próximos."""
from __future__ import annotations

from langchain_core.documents import Document

from chatbot_backend.app.services.chat_service import ChatbotService


def test_prioriza_documentos_com_o_tema() -> None:
    docs = [
        Document(page_content="Discurso sobre pisos salariais e orçamento."),
        Document(page_content="A GREVE dos servidores precisa de resposta."),
        Document(page_content="Votação da PEC do plenário."),
        Document(page_content="Apoio à greve geral da categoria."),
    ]

    ordered = ChatbotService._prioritize_topic_documents(docs, "greve")

    assert [d.page_content for d in ordered[:2]] == [
        "A GREVE dos servidores precisa de resposta.",
        "Apoio à greve geral da categoria.",
    ]
    # Ordenação estável dentro de cada grupo.
    assert [d.page_content for d in ordered[2:]] == [
        "Discurso sobre pisos salariais e orçamento.",
        "Votação da PEC do plenário.",
    ]


def test_sem_match_mantem_ordem_original() -> None:
    docs = [Document(page_content="a"), Document(page_content="b")]
    ordered = ChatbotService._prioritize_topic_documents(docs, "greve")
    assert [d.page_content for d in ordered] == ["a", "b"]


def test_dedupe_limita_chunks_por_discurso() -> None:
    """Caso real: busca global devolveu chunk repetido e 3+ trechos do mesmo
    discurso — o contexto virava um orador só."""
    def doc(chunk_id: str, source: str) -> Document:
        return Document(
            page_content=chunk_id,
            metadata={"chunk_id": chunk_id, "source": source},
        )

    docs = [
        doc("a:0", "a"),
        doc("a:0", "a"),  # chunk repetido exato
        doc("a:1", "a"),
        doc("a:2", "a"),  # 3º chunk do mesmo discurso — descartado
        doc("b:0", "b"),
    ]
    result = ChatbotService._dedupe_documents(docs)
    assert [d.page_content for d in result] == ["a:0", "a:1", "b:0"]
