"""Testes da formatação do contexto entregue ao LLM.

Os chunks recuperados carregam o parlamentar em `cmetadata`, mas o cabeçalho
montado para o prompt só expunha `Fonte:` e `Data:`. O modelo recebia o trecho
sem saber de quem era a fala — e respondia que não tinha informação sobre o
parlamentar perguntado.
"""

from __future__ import annotations

from langchain_core.documents import Document

from chatbot_backend.app.services.chat_service import ChatbotService


def test_contexto_identifica_o_parlamentar_do_trecho() -> None:
    document = Document(
        page_content="O banco central precisa de autonomia.",
        metadata={
            "source": "speeches_transcripts:4242",
            "date": "2026-03-10",
            "parliamentarian": "Flávio Bolsonaro",
        },
    )

    formatted = ChatbotService._format_documents([document])

    assert "Flávio Bolsonaro" in formatted


def test_contexto_preserva_fonte_data_e_conteudo() -> None:
    document = Document(
        page_content="O banco central precisa de autonomia.",
        metadata={
            "source": "speeches_transcripts:4242",
            "date": "2026-03-10",
            "parliamentarian": "Flávio Bolsonaro",
        },
    )

    formatted = ChatbotService._format_documents([document])

    assert "speeches_transcripts:4242" in formatted
    assert "2026-03-10" in formatted
    assert "O banco central precisa de autonomia." in formatted


def test_contexto_inclui_partido_e_uf_quando_disponiveis() -> None:
    document = Document(
        page_content="Discurso.",
        metadata={
            "source": "speeches_transcripts:1",
            "parliamentarian": "Flávio Bolsonaro",
            "party": "PL",
            "state": "RJ",
        },
    )

    formatted = ChatbotService._format_documents([document])

    assert "PL" in formatted
    assert "RJ" in formatted


def test_trecho_sem_parlamentar_continua_sendo_formatado() -> None:
    document = Document(
        page_content="Discurso sem autoria conhecida.",
        metadata={"source": "speeches_transcripts:9"},
    )

    formatted = ChatbotService._format_documents([document])

    assert "speeches_transcripts:9" in formatted
    assert "Discurso sem autoria conhecida." in formatted
