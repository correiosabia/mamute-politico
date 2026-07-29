"""Teto de tokens por requisição da API de embeddings.

A carga inicial quebrou em produção no lote 725:

    openai.BadRequestError: Error code: 400 -
    Requested 302183 tokens, max 300000 tokens per request

A causa foi limitar o lote por *quantidade de discursos* enquanto a API limita
por *token*. Discursos antigos são muito mais longos: o lote 1 gerou 362 chunks
para 100 discursos, o lote 723 gerou 1.208 — 3,3x mais denso pelo mesmo número
de linhas. Nenhum `--batch-size` fixo é seguro contra isso.

A trava real é o `chunk_size` do OpenAIEmbeddings, que limita quantos textos vão
em cada requisição HTTP independente do tamanho do lote que o script montou.
"""

from __future__ import annotations

import pytest

from chatbot_backend.app.core.config import Settings
from chatbot_backend.app.services import vector_store


@pytest.fixture(autouse=True)
def _limpa_cache():
    vector_store.get_embeddings.cache_clear()
    yield
    vector_store.get_embeddings.cache_clear()


def test_embeddings_limitam_textos_por_requisicao() -> None:
    embeddings = vector_store.get_embeddings()

    assert embeddings.chunk_size == vector_store.settings.openai_embeddings_batch_size


def test_teto_padrao_cabe_com_folga_no_limite_da_api() -> None:
    """200 chunks de ~1200 caracteres ficam na casa de 80k tokens, contra 300k."""

    assert Settings.model_fields["openai_embeddings_batch_size"].default == 200


def test_teto_e_configuravel_por_ambiente(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_EMBEDDINGS_BATCH_SIZE", "50")
    from chatbot_backend.app.core.config import get_settings

    get_settings.cache_clear()
    try:
        assert get_settings().openai_embeddings_batch_size == 50
    finally:
        get_settings.cache_clear()


def test_teto_precisa_ser_positivo(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_EMBEDDINGS_BATCH_SIZE", "0")
    from chatbot_backend.app.core.config import get_settings

    get_settings.cache_clear()
    try:
        with pytest.raises(Exception):
            get_settings()
    finally:
        get_settings.cache_clear()
