from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, rel: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cam = load_module(
    "test_camara_speeches_datafim_module",
    "mamute_scrappers/camara_crawler/speeches_transcripts.py",
)
bf = load_module(
    "test_backfill_vs_module",
    "mamute_scrappers/scripts/backfill_votes_speeches.py",
)


def test_fetch_speeches_list_sends_data_fim(monkeypatch) -> None:
    """A API da Câmara limita o range a 4 anos; o crawler precisa enviar dataFim."""
    captured = {}

    def fake_request(url, params=None):
        captured["params"] = params
        return {"dados": []}

    monkeypatch.setattr(cam, "_request_json", fake_request)
    cam._fetch_speeches_list(123, "2019-01-01", page=1, data_fim="2019-12-31")

    assert captured["params"].get("dataFim") == "2019-12-31"
    assert captured["params"].get("dataInicio") == "2019-01-01"


def test_camara_speeches_chunks_windows_within_4_years(monkeypatch) -> None:
    """Cada chunk de discurso da Câmara deve ter janela <= 4 anos (data_inicio+data_fim)."""
    monkeypatch.setattr(bf, "_parliamentarian_codes", lambda house: [123])

    chunks = bf._camara_speeches_chunks()

    assert chunks, "deve gerar ao menos um chunk"
    for c in chunks:
        assert "data_inicio" in c and "data_fim" in c
        ini = int(c["data_inicio"][:4])
        fim = int(c["data_fim"][:4])
        assert 0 <= fim - ini <= 4, f"janela maior que 4 anos: {c['data_inicio']}..{c['data_fim']}"
    # cobre o piso historico
    anos = {int(c["data_inicio"][:4]) for c in chunks}
    assert bf.SINCE_YEAR in anos
