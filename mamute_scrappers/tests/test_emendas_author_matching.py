from __future__ import annotations

from mamute_scrappers.portal_crawler import author_matching as matching

Candidate = matching.ParliamentarianCandidate


def candidates():
    return [
        Candidate(id=1, name="José da Silva", full_name="José da Silva Júnior"),
        Candidate(id=2, name="Maria Souza", full_name="Maria de Souza Lima"),
        Candidate(id=3, name="Chico Alencar", full_name="Francisco Rodrigues Alencar"),
    ]


def test_casa_pelo_nome_parlamentar():
    result = matching.match_author("José da Silva", candidates())
    assert result.parliamentarian_id == 1
    assert result.status == matching.MATCH_STATUS_MATCHED


def test_casa_ignorando_acento_e_caixa():
    result = matching.match_author("JOSE DA SILVA", candidates())
    assert result.parliamentarian_id == 1
    assert result.status == matching.MATCH_STATUS_MATCHED


def test_casa_ignorando_espaco_duplicado():
    result = matching.match_author("Maria   Souza", candidates())
    assert result.parliamentarian_id == 2
    assert result.status == matching.MATCH_STATUS_MATCHED


def test_casa_pelo_nome_civil_quando_nome_parlamentar_nao_bate():
    # O Portal publica o nome civil; a nossa base guarda o nome de guerra.
    result = matching.match_author("Francisco Rodrigues Alencar", candidates())
    assert result.parliamentarian_id == 3
    assert result.status == matching.MATCH_STATUS_MATCHED


def test_nome_parlamentar_tem_precedencia_sobre_nome_civil():
    conflito = [
        Candidate(id=10, name="Ana Paula", full_name="Ana Paula Ferreira"),
        Candidate(id=11, name="Ana Paula Ferreira", full_name="Ana Paula Ferreira"),
    ]
    # "Ana Paula" casa exatamente com o `name` de 10 e com nada de 11.
    result = matching.match_author("Ana Paula", conflito)
    assert result.parliamentarian_id == 10
    assert result.status == matching.MATCH_STATUS_MATCHED


def test_sem_candidato_devolve_unmatched():
    result = matching.match_author("Fulano Inexistente", candidates())
    assert result.parliamentarian_id is None
    assert result.status == matching.MATCH_STATUS_UNMATCHED


def test_homonimo_devolve_ambiguous_sem_escolher():
    homonimos = [
        Candidate(id=4, name="João Silva", full_name="João Silva Neto"),
        Candidate(id=5, name="João Silva", full_name="João Silva Filho"),
    ]
    result = matching.match_author("João Silva", homonimos)
    assert result.parliamentarian_id is None
    assert result.status == matching.MATCH_STATUS_AMBIGUOUS


def test_autor_vazio_devolve_unmatched():
    for vazio in ("", "   ", None):
        result = matching.match_author(vazio, candidates())
        assert result.parliamentarian_id is None
        assert result.status == matching.MATCH_STATUS_UNMATCHED


def test_lista_de_candidatos_vazia_devolve_unmatched():
    result = matching.match_author("José da Silva", [])
    assert result.parliamentarian_id is None
    assert result.status == matching.MATCH_STATUS_UNMATCHED


def test_candidato_com_campos_nulos_nao_quebra():
    parciais = [Candidate(id=6, name=None, full_name=None)]
    result = matching.match_author("Qualquer Nome", parciais)
    assert result.status == matching.MATCH_STATUS_UNMATCHED


def test_nao_faz_casamento_aproximado():
    # Um caractere de diferenca nao pode casar: atribuir dinheiro publico por
    # semelhanca e o erro que este modulo existe para evitar.
    result = matching.match_author("Jose da Silvo", candidates())
    assert result.parliamentarian_id is None
    assert result.status == matching.MATCH_STATUS_UNMATCHED


def test_casa_nome_em_caixa_alta_como_a_fonte_publica():
    # Formato real do Portal: nome parlamentar em caixa alta.
    reais = [
        Candidate(id=20, name="Heitor Schuch", full_name="Heitor José Schuch"),
        Candidate(id=21, name="Adriano do Baldy", full_name=None),
    ]
    assert matching.match_author("HEITOR SCHUCH", reais).parliamentarian_id == 20
    assert matching.match_author("ADRIANO DO BALDY", reais).parliamentarian_id == 21
