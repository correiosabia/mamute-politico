from __future__ import annotations

from mamute_scrappers.scripts import backfill_emendas as backfill


def test_um_chunk_por_ano_do_intervalo():
    chunks = backfill.build_chunks(2022, 2026)
    assert [c["ano"] for c in chunks] == [2022, 2023, 2024, 2025, 2026]


def test_cada_chunk_tem_key_estavel():
    chunks = backfill.build_chunks(2022, 2023)
    assert [c["key"] for c in chunks] == ["emendas-2022", "emendas-2023"]


def test_intervalo_invertido_devolve_lista_vazia():
    assert backfill.build_chunks(2026, 2022) == []


def test_ano_unico_devolve_um_chunk():
    assert len(backfill.build_chunks(2026, 2026)) == 1


def test_backfill_comeca_em_2022():
    # O ticket pediu "comecando por 2026"; o backfill ate 2022 foi decisao de
    # produto registrada na spec.
    assert backfill.SINCE_YEAR == 2022


def test_estado_e_gravado_de_forma_atomica(tmp_path, monkeypatch):
    # Grava em .tmp e move: um kill no meio da escrita nao deixa JSON truncado.
    state_file = tmp_path / "backfill_emendas.json"
    monkeypatch.setattr(backfill, "STATE_FILE", state_file)

    backfill._save_state({"done": ["emendas-2022"]})

    assert state_file.exists()
    assert not state_file.with_suffix(".json.tmp").exists()
    assert backfill._load_state()["done"] == ["emendas-2022"]


def test_estado_ilegivel_recomeca_do_zero_sem_quebrar(tmp_path, monkeypatch):
    state_file = tmp_path / "backfill_emendas.json"
    state_file.write_text("{ isso nao e json", encoding="utf-8")
    monkeypatch.setattr(backfill, "STATE_FILE", state_file)

    assert backfill._load_state() == {"done": [], "updated_at": None}
