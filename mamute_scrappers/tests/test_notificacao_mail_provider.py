from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, rel: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # necessário para @dataclass resolver o módulo
    spec.loader.exec_module(mod)
    return mod


cfg = load_module(
    "test_notificacao_config_module",
    "mamute_scrappers/scripts/notificacao/config.py",
)

# Todas as vars de e-mail que podem interferir entre cenários.
_ALL_MAIL_ENV = [
    "MAIL_PROVIDER",
    "SMTP_USER", "SMTP_PASSWD", "SMTP_SENDER", "SMTP_SERVER", "SMTP_PORT", "SMTP_FROM_NAME",
    "MAILGUN_SMTP_USER", "MAILGUN_SMTP_PASSWD", "MAILGUN_SMTP_SENDER",
    "MAILGUN_SMTP_SERVER", "MAILGUN_SMTP_PORT", "MAILGUN_SMTP_FROM_NAME",
    "SES_SMTP_USER", "SES_SMTP_PASSWD", "SES_SMTP_SENDER",
    "SES_SMTP_SERVER", "SES_SMTP_PORT", "SES_SMTP_FROM_NAME",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in _ALL_MAIL_ENV:
        monkeypatch.delenv(k, raising=False)
    # sender/from_name comuns quase sempre presentes
    monkeypatch.setenv("SMTP_SENDER", "relatorios@mamutepolitico.com.br")
    monkeypatch.setenv("SMTP_FROM_NAME", "Mamute Politico")


def test_provider_mailgun_uses_mailgun_creds(monkeypatch):
    monkeypatch.setenv("MAIL_PROVIDER", "mailgun")
    monkeypatch.setenv("MAILGUN_SMTP_USER", "noreply@mamutepolitico.com.br")
    monkeypatch.setenv("MAILGUN_SMTP_PASSWD", "mg-secret")
    monkeypatch.setenv("MAILGUN_SMTP_SERVER", "smtp.mailgun.org")
    # SES tambem presente, para provar que NAO e usado
    monkeypatch.setenv("SES_SMTP_USER", "AKIA-ses")
    monkeypatch.setenv("SES_SMTP_PASSWD", "ses-secret")
    monkeypatch.setenv("SES_SMTP_SERVER", "email-smtp.sa-east-1.amazonaws.com")

    c = cfg.get_smtp_config()
    assert c.server == "smtp.mailgun.org"
    assert c.user == "noreply@mamutepolitico.com.br"
    assert c.password == "mg-secret"


def test_provider_ses_uses_ses_creds(monkeypatch):
    monkeypatch.setenv("MAIL_PROVIDER", "ses")
    monkeypatch.setenv("SES_SMTP_USER", "AKIA-ses")
    monkeypatch.setenv("SES_SMTP_PASSWD", "ses-secret")
    monkeypatch.setenv("SES_SMTP_SERVER", "email-smtp.sa-east-1.amazonaws.com")
    monkeypatch.setenv("MAILGUN_SMTP_USER", "noreply@mamutepolitico.com.br")
    monkeypatch.setenv("MAILGUN_SMTP_PASSWD", "mg-secret")
    monkeypatch.setenv("MAILGUN_SMTP_SERVER", "smtp.mailgun.org")

    c = cfg.get_smtp_config()
    assert c.server == "email-smtp.sa-east-1.amazonaws.com"
    assert c.user == "AKIA-ses"
    assert c.password == "ses-secret"


def test_no_provider_falls_back_to_legacy_smtp(monkeypatch):
    """Sem MAIL_PROVIDER, mantem o comportamento antigo (SMTP_*)."""
    monkeypatch.setenv("SMTP_USER", "legacy-user")
    monkeypatch.setenv("SMTP_PASSWD", "legacy-pass")
    monkeypatch.setenv("SMTP_SERVER", "email-smtp.sa-east-1.amazonaws.com")

    c = cfg.get_smtp_config()
    assert c.user == "legacy-user"
    assert c.server == "email-smtp.sa-east-1.amazonaws.com"


def test_provider_specific_falls_back_to_common_sender(monkeypatch):
    """Sender/from_name comuns (SMTP_SENDER) valem quando nao ha override do provedor."""
    monkeypatch.setenv("MAIL_PROVIDER", "mailgun")
    monkeypatch.setenv("MAILGUN_SMTP_USER", "noreply@mamutepolitico.com.br")
    monkeypatch.setenv("MAILGUN_SMTP_PASSWD", "mg-secret")
    monkeypatch.setenv("MAILGUN_SMTP_SERVER", "smtp.mailgun.org")

    c = cfg.get_smtp_config()
    assert c.sender == "relatorios@mamutepolitico.com.br"
    assert c.from_name == "Mamute Politico"
