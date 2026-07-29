"""Testes da estratégia de tipo/índice da coluna de embeddings.

O pgvector recusa índice (HNSW ou IVFFlat) em colunas `vector` com mais de 2000
dimensões. O modelo em uso — `text-embedding-3-large` — devolve 3072, e trocá-lo
não é opção. A saída é armazenar em `halfvec`, que indexa até 4000 dimensões,
preservando todas as 3072 dimensões do vetor.

Medido em produção (20k linhas, pgvector 0.8.2):
  vector(3072) sem índice ......... 712 ms
  halfvec(3072) + HNSW ............   5 ms
"""

from __future__ import annotations

import pytest

from chatbot_backend.scripts import init_vector_collection as ivc


class TestTipoDaColuna:
    def test_acima_de_2000_dimensoes_usa_halfvec(self) -> None:
        assert ivc.vector_column_type(3072) == "halfvec(3072)"

    def test_ate_2000_dimensoes_usa_vector(self) -> None:
        assert ivc.vector_column_type(1536) == "vector(1536)"

    def test_limite_exato_de_2000_ainda_e_vector(self) -> None:
        assert ivc.vector_column_type(2000) == "vector(2000)"
        assert ivc.vector_column_type(2001) == "halfvec(2001)"


class TestOperatorClass:
    def test_halfvec_usa_operator_class_propria(self) -> None:
        assert ivc.vector_index_opclass(3072) == "halfvec_cosine_ops"

    def test_vector_usa_operator_class_padrao(self) -> None:
        assert ivc.vector_index_opclass(1536) == "vector_cosine_ops"


class TestDDLDoIndice:
    def test_3072_gera_alter_para_halfvec(self) -> None:
        ddl = "\n".join(ivc.build_vector_index_statements(3072))

        assert "ALTER TABLE" in ddl
        assert "halfvec(3072)" in ddl

    def test_3072_gera_indice_hnsw_e_nao_ivfflat(self) -> None:
        ddl = "\n".join(ivc.build_vector_index_statements(3072))

        assert "USING hnsw" in ddl
        assert "halfvec_cosine_ops" in ddl
        assert "ivfflat" not in ddl.lower()

    def test_1536_tambem_usa_hnsw(self) -> None:
        """HNSW tem recall melhor que IVFFlat e não exige tuning de `lists`."""

        ddl = "\n".join(ivc.build_vector_index_statements(1536))

        assert "USING hnsw" in ddl
        assert "vector_cosine_ops" in ddl
        assert "halfvec" not in ddl

    def test_alter_preserva_os_dados_existentes_com_cast(self) -> None:
        ddl = "\n".join(ivc.build_vector_index_statements(3072))

        assert "USING embedding::halfvec(3072)" in ddl

    @pytest.mark.parametrize("dimension", [1536, 3072])
    def test_indice_e_idempotente(self, dimension: int) -> None:
        ddl = "\n".join(ivc.build_vector_index_statements(dimension))

        assert "IF NOT EXISTS" in ddl
