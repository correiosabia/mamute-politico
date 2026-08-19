from __future__ import annotations

from mamute_scrappers.scripts import backfill_cota as backfill


def test_um_chunk_por_ano_e_casa_intercalado_por_ano():
    chunks = backfill.build_chunks(2022, 2023)
    assert [c["key"] for c in chunks] == [
        "cota-camara-2022",
        "cota-senado-2022",
        "cota-camara-2023",
        "cota-senado-2023",
    ]


def test_chunk_carrega_modulo_e_ano():
    chunks = backfill.build_chunks(2026, 2026)
    assert chunks[0]["module"] == "mamute_scrappers.camara_crawler.expenses"
    assert chunks[1]["module"] == "mamute_scrappers.senado_crawler.expenses"
    assert all(c["ano"] == 2026 for c in chunks)


def test_intervalo_invertido_devolve_lista_vazia():
    assert backfill.build_chunks(2026, 2022) == []


def test_backfill_comeca_em_2022():
    # Cobertura 2022 -> hoje, decisao de produto registrada na spec da CS-57.
    assert backfill.SINCE_YEAR == 2022


def test_estado_e_gravado_de_forma_atomica(tmp_path, monkeypatch):
    state_file = tmp_path / "backfill_cota.json"
    monkeypatch.setattr(backfill, "STATE_FILE", state_file)

    backfill._save_state({"done": ["cota-camara-2022"]})

    assert state_file.exists()
    assert not state_file.with_suffix(".json.tmp").exists()
    assert backfill._load_state()["done"] == ["cota-camara-2022"]


def test_estado_ilegivel_recomeca_do_zero_sem_quebrar(tmp_path, monkeypatch):
    state_file = tmp_path / "backfill_cota.json"
    state_file.write_text("{ isso nao e json", encoding="utf-8")
    monkeypatch.setattr(backfill, "STATE_FILE", state_file)

    assert backfill._load_state() == {"done": [], "updated_at": None}
