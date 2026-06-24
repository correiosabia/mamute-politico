from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from bs4 import BeautifulSoup


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, relative_path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


speechs_transcipts = _load(
    "test_senado_speechs_transcipts",
    "mamute_scrappers/senado_crawler/speechs_transcipts.py",
)


def _list_row(href: str):
    html = f"""
    <tr>
      <td><a href="{href}">01/02/2026</a></td>
      <td>Pronunciamento</td>
      <td>Senado Federal</td>
      <td>PT - SP</td>
      <td>Resumo do discurso</td>
    </tr>
    """
    return BeautifulSoup(html, "html.parser").find("tr")


def test_parse_list_row_accepts_relative_senado_detail_link() -> None:
    payload = speechs_transcipts._parse_list_row(
        _list_row("/web/atividade/pronunciamentos/-/p/texto/123456")
    )

    assert payload is not None
    assert (
        payload["speech_link"]
        == "https://www25.senado.leg.br/web/atividade/pronunciamentos/-/p/texto/123456"
    )


def test_parse_list_row_rejects_external_detail_link() -> None:
    payload = speechs_transcipts._parse_list_row(
        _list_row("http://169.254.169.254/latest/meta-data")
    )

    assert payload is None


def test_parse_list_row_rejects_script_scheme_detail_link() -> None:
    payload = speechs_transcipts._parse_list_row(_list_row("javascript:alert(1)"))

    assert payload is None
