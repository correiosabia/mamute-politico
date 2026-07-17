from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, rel: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cam = load_module(
    "test_camara_parliamentarian_ingestion_scope_module",
    "mamute_scrappers/camara_crawler/parliamentarian.py",
)


def test_ingestion_scope_uses_safe_default_for_missing_or_invalid_values(monkeypatch, caplog) -> None:
    monkeypatch.delenv(cam.MAMUTE_CAMARA_INGEST_SCOPE, raising=False)
    assert cam.get_camara_ingestion_scope(None) is cam.CamaraIngestionScope.CURRENT_ONLY
    assert (
        cam.get_camara_ingestion_scope("current_and_licensed")
        is cam.CamaraIngestionScope.CURRENT_AND_LICENSED
    )
    assert cam.get_camara_ingestion_scope("unexpected") is cam.CamaraIngestionScope.CURRENT_ONLY
    assert "padrão seguro" in caplog.text


def test_expanded_scopes_query_the_current_legislature(monkeypatch) -> None:
    requests = []

    def fake_request(url, *, params=None):
        requests.append((url, params))
        if url.endswith("/legislaturas"):
            return {
                "dados": [
                    {"id": 57, "dataInicio": "2023-02-01", "dataFim": "2027-01-31"},
                ]
            }
        return {"dados": [{"id": 220639, "nome": "Guilherme Boulos"}]}

    monkeypatch.setattr(cam, "_request_json", fake_request)
    legislature_id = cam._fetch_current_legislature_id(reference_date=cam.date(2026, 7, 17))
    assert legislature_id == 57
    assert requests == [(f"{cam.CAMARA_API_BASE_URL}/legislaturas", None)]

    monkeypatch.setattr(cam, "_fetch_current_legislature_id", lambda: 57)

    deputies = cam._fetch_parliamentarian_list(cam.CamaraIngestionScope.CURRENT_LEGISLATURE)
    assert deputies == [{"id": 220639, "nome": "Guilherme Boulos"}]
    assert requests[-1][1]["idLegislatura"] == "57"


def test_current_and_licensed_scope_keeps_boulos_like_record(monkeypatch) -> None:
    basic_records = [{"id": 220639}, {"id": 999999}]
    payloads = {
        220639: {
            "parliamentarian_code": 220639,
            "name": "Guilherme Boulos",
            "status": "Licenciado",
            "social_networks": [],
        },
        999999: {
            "parliamentarian_code": 999999,
            "name": "Ex-deputado",
            "status": "Fim de mandato",
            "social_networks": [],
        },
    }
    monkeypatch.setattr(cam, "_fetch_parliamentarian_list", lambda scope: basic_records)
    monkeypatch.setattr(cam, "_build_payload_from_json", lambda item: payloads[item["id"]])

    records = list(
        cam._fetch_parliamentarians(scope=cam.CamaraIngestionScope.CURRENT_AND_LICENSED)
    )

    assert [record["parliamentarian_code"] for record in records] == [220639]
    assert records[0]["status"] == "Licenciado"


def test_upsert_updates_existing_record_without_deleting_it(monkeypatch) -> None:
    class FakeParliamentarian:
        def __init__(self, parliamentarian_code):
            self.id = 1
            self.parliamentarian_code = parliamentarian_code

    class FakeQuery:
        def __init__(self, record):
            self.record = record

        def filter_by(self, **_kwargs):
            return self

        def one_or_none(self):
            return self.record

    class FakeSession:
        def __init__(self):
            self.record = None
            self.added = []
            self.deleted = []

        def query(self, _model):
            return FakeQuery(self.record)

        def add(self, record):
            self.added.append(record)
            self.record = record

        def delete(self, record):
            self.deleted.append(record)

    session = FakeSession()
    monkeypatch.setattr(cam, "Parliamentarian", FakeParliamentarian)
    monkeypatch.setattr(cam, "ParliamentarianSocialNetwork", object)
    monkeypatch.setattr(cam, "SocialNetwork", object)
    monkeypatch.setattr(cam, "_sync_social_networks", lambda *_args: None)

    first = cam._upsert_parliamentarian(
        session,
        {"parliamentarian_code": 220639, "name": "Guilherme Boulos", "social_networks": []},
    )
    second = cam._upsert_parliamentarian(
        session,
        {"parliamentarian_code": 220639, "name": "Guilherme Boulos atualizado", "social_networks": []},
    )

    assert first is second
    assert second.name == "Guilherme Boulos atualizado"
    assert len(session.added) == 1
    assert session.deleted == []
