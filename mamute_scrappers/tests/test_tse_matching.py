from __future__ import annotations

from mamute_scrappers.tse_crawler.matching import (
    MATCH_STATUS_AMBIGUOUS,
    MATCH_STATUS_CPF,
    MATCH_STATUS_NAME,
    MATCH_STATUS_UNMATCHED,
    ParliamentarianRecord,
    build_index,
    match_candidacy,
)

DEPUTADO = ParliamentarianRecord(
    id=1,
    name="Heitor Schuch",
    full_name="Heitor José Schuch",
    cpf="11122233344",
    state_elected="RS",
)
SENADOR = ParliamentarianRecord(
    id=2,
    name="Marcos Rogério",
    full_name="Marcos Rogério da Silva Brito",
    cpf=None,
    state_elected="RO",
)
HOMONIMO_SP = ParliamentarianRecord(
    id=3, name="João Silva", full_name="João da Silva", cpf=None, state_elected="SP"
)
HOMONIMO_BA = ParliamentarianRecord(
    id=4, name="João Silva", full_name="João da Silva", cpf=None, state_elected="BA"
)
HOMONIMO_SP_2 = ParliamentarianRecord(
    id=5, name="João Silva", full_name="João da Silva Junior", cpf=None,
    state_elected="SP",
)

INDEX = build_index([DEPUTADO, SENADOR, HOMONIMO_SP, HOMONIMO_BA, HOMONIMO_SP_2])


def test_cpf_casa_mesmo_com_nome_diferente():
    result = match_candidacy(
        cpf="111.222.333-44",
        full_name="NOME COMPLETAMENTE OUTRO",
        ballot_name="OUTRO",
        state="RS",
        index=INDEX,
    )
    assert result.parliamentarian_id == 1
    assert result.status == MATCH_STATUS_CPF


def test_senador_sem_cpf_casa_por_nome_completo():
    result = match_candidacy(
        cpf=None,
        full_name="MARCOS ROGÉRIO DA SILVA BRITO",
        ballot_name="MARCOS ROGERIO",
        state="RO",
        index=INDEX,
    )
    assert result.parliamentarian_id == 2
    assert result.status == MATCH_STATUS_NAME


def test_nome_de_urna_tambem_casa():
    result = match_candidacy(
        cpf=None,
        full_name="NOME CIVIL DIVERGENTE",
        ballot_name="MARCOS ROGÉRIO",
        state="RO",
        index=INDEX,
    )
    assert result.parliamentarian_id == 2
    assert result.status == MATCH_STATUS_NAME


def test_homonimo_desempata_por_uf():
    result = match_candidacy(
        cpf=None,
        full_name="JOÃO DA SILVA",
        ballot_name="JOAO SILVA",
        state="BA",
        index=INDEX,
    )
    assert result.parliamentarian_id == 4
    assert result.status == MATCH_STATUS_NAME


def test_homonimos_na_mesma_uf_sao_ambiguos():
    # "Joao Silva" (nome parlamentar) existe duas vezes em SP: ids 3 e 5.
    result = match_candidacy(
        cpf=None,
        full_name="JOÃO SILVA",
        ballot_name=None,
        state="SP",
        index=INDEX,
    )
    assert result.parliamentarian_id is None
    assert result.status == MATCH_STATUS_AMBIGUOUS


def test_homonimos_todos_em_outras_ufs_nao_casam():
    # Homonimos existem em SP e BA, mas a candidatura e em MG: nenhum vale.
    result = match_candidacy(
        cpf=None,
        full_name="JOÃO DA SILVA",
        ballot_name="JOAO SILVA",
        state="MG",
        index=INDEX,
    )
    assert result.parliamentarian_id is None
    assert result.status == MATCH_STATUS_UNMATCHED


def test_homonimo_em_uf_errada_nao_casa():
    """Regressao da carga inicial de 2026-08-08: 'Eduardo Gomes' (senador por
    TO) casou com candidato homonimo a dep. estadual no AC. Hit unico de nome
    nao basta: a UF da candidatura precisa bater com a UF de eleicao."""
    result = match_candidacy(
        cpf=None,
        full_name="MARCOS ROGÉRIO DA SILVA BRITO",
        ballot_name="MARCOS ROGERIO",
        state="AC",
        index=INDEX,
    )
    assert result.parliamentarian_id is None
    assert result.status == MATCH_STATUS_UNMATCHED


def test_presidente_casa_sem_filtro_de_uf():
    """Candidatura a presidente tem state='BR'; a UF de eleicao nunca bateria.

    Hit unico nacional vale para o cargo nacional."""
    result = match_candidacy(
        cpf=None,
        full_name="MARCOS ROGÉRIO DA SILVA BRITO",
        ballot_name="MARCOS ROGERIO",
        state="BR",
        index=INDEX,
    )
    assert result.parliamentarian_id == 2
    assert result.status == MATCH_STATUS_NAME


def test_desconhecido_nao_casa():
    result = match_candidacy(
        cpf="99988877766",
        full_name="PESSOA NOVA NA POLITICA",
        ballot_name="NOVATO",
        state="SP",
        index=INDEX,
    )
    assert result.parliamentarian_id is None
    assert result.status == MATCH_STATUS_UNMATCHED
