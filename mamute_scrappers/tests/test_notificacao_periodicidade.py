"""Quinzenal (fortnight) é uma periodicidade de produção de primeira classe."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, rel: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


cfg = _load(
    "test_notificacao_periodicidade_config",
    "mamute_scrappers/scripts/notificacao/config.py",
)


def test_fortnight_is_production_periodicity() -> None:
    assert "fortnight" in cfg.PERIODICIDADES_PRODUCAO
    assert "fortnight" in cfg.PERIODICIDADES_VALIDAS


def test_fortnight_window_is_15_days() -> None:
    assert cfg.PERIOD_DAYS["fortnight"] == 15


def test_fortnight_has_subject_and_highlight_limit() -> None:
    assert cfg.subject_for_periodicidade("fortnight") == "Relatório quinzenal"
    assert cfg.default_highlight_limit("fortnight") == 9


def test_all_production_periodicities_have_windows_and_subjects() -> None:
    for p in cfg.PERIODICIDADES_PRODUCAO:
        assert cfg.PERIOD_DAYS.get(p) is not None
        # rótulo específico (não cai no genérico "Relatório")
        assert cfg.subject_for_periodicidade(p) != "Relatório"
