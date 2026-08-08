from __future__ import annotations

from datetime import datetime

from mamute_scrappers.tse_crawler import parsing

LISTING_ITEM = {
    "id": 10002536710,
    "nomeUrna": "DR. JUNIOR FEITOSA",
    "numero": 277,
    "nomeCompleto": "RIBAMAR DE SOUSA FEITOZA JÚNIOR",
    "tituloEleitor": "003576712402",
    "cpf": None,
    "descricaoSituacao": "Aguardando julgamento",
    "descricaoTotalizacao": "Concorrendo",
    "ufCandidatura": "AC",
    "nomeColigacao": "DC",
    "partido": {"numero": 27, "sigla": "DC", "nome": "Democracia Crista"},
}

DETAIL = {
    "id": 10002536710,
    "cpf": "67146902234",
    "tituloEleitor": "003576712402",
    "fotoUrl": "https://divulgacandcontas.tse.jus.br/divulga/rest/arquivo/img/20322002026/10002536710/AC",
    "dataUltimaAtualizacao": "2026-08-05 11:25",
}


def test_normalize_cpf_aceita_so_11_digitos():
    assert parsing.normalize_cpf("671.469.022-34") == "67146902234"
    assert parsing.normalize_cpf("67146902234") == "67146902234"
    assert parsing.normalize_cpf("123") is None
    assert parsing.normalize_cpf(None) is None


def test_parse_tse_datetime():
    assert parsing.parse_tse_datetime("2026-08-05 11:25") == datetime(2026, 8, 5, 11, 25)
    assert parsing.parse_tse_datetime(None) is None
    assert parsing.parse_tse_datetime("nao-e-data") is None


def test_fingerprint_estavel_e_sensivel_a_mudanca():
    fp1 = parsing.compute_listing_fingerprint(LISTING_ITEM)
    fp2 = parsing.compute_listing_fingerprint(dict(LISTING_ITEM))
    assert fp1 == fp2

    mudado = dict(LISTING_ITEM, descricaoSituacao="Deferido")
    assert parsing.compute_listing_fingerprint(mudado) != fp1


def test_fingerprint_ignora_campos_volateis():
    com_ruido = dict(LISTING_ITEM, fotoUrl="http://x/y.jpg")
    assert parsing.compute_listing_fingerprint(com_ruido) == (
        parsing.compute_listing_fingerprint(LISTING_ITEM)
    )


def test_build_listing_payload():
    payload = parsing.build_listing_payload(
        LISTING_ITEM,
        election_year=2026,
        office_code=5,
        office_name="Senador",
        state="AC",
    )
    assert payload == {
        "election_year": 2026,
        "tse_candidate_id": 10002536710,
        "office_code": 5,
        "office": "Senador",
        "state": "AC",
        "ballot_number": 277,
        "ballot_name": "DR. JUNIOR FEITOSA",
        "full_name": "RIBAMAR DE SOUSA FEITOZA JÚNIOR",
        "party": "DC",
        "coalition": "DC",
        "status": "Aguardando julgamento",
        "totalization_status": "Concorrendo",
    }


def test_build_listing_payload_sem_id_descarta():
    assert (
        parsing.build_listing_payload(
            {"nomeUrna": "X"},
            election_year=2026,
            office_code=5,
            office_name="Senador",
            state="AC",
        )
        is None
    )


def test_merge_detail_payload():
    payload = parsing.build_listing_payload(
        LISTING_ITEM,
        election_year=2026,
        office_code=5,
        office_name="Senador",
        state="AC",
    )
    merged = parsing.merge_detail_payload(payload, DETAIL)
    assert merged["cpf"] == "67146902234"
    assert merged["voter_id"] == "003576712402"
    assert merged["photo_url"].startswith("https://divulgacandcontas")
    assert merged["tse_last_update"] == datetime(2026, 8, 5, 11, 25)
    assert merged["details"] == DETAIL
