"""Configuração de ambiente e branding dos e-mails."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_PACKAGE_DIR = Path(__file__).resolve().parent
_MAMUTE_ROOT = _PACKAGE_DIR.parents[1]
_REPO_ROOT = _MAMUTE_ROOT.parent

_ENV_CANDIDATES = [
    _PACKAGE_DIR / ".env",
    _MAMUTE_ROOT / ".env",
    _REPO_ROOT / ".env",
    _REPO_ROOT / "scripts" / ".env",
]

for _path in _ENV_CANDIDATES:
    if _path.exists():
        load_dotenv(_path, override=False)

# Produção: filtradas pelo tier (`periodicidade_email`).
PERIODICIDADES_PRODUCAO = frozenset({"day", "week", "month"})
# Teste: amostra limitada, sem filtro de tier.
PERIODICIDADE_TESTE = "total"
PERIODICIDADES_VALIDAS = PERIODICIDADES_PRODUCAO | {PERIODICIDADE_TESTE}

PERIOD_DAYS: dict[str, int | None] = {
    "day": 1,
    "week": 7,
    "month": 30,
    "total": None,
}

DEFAULT_HIGHLIGHT_LIMIT = {
    "day": 9,
    "week": 9,
    "month": 9,
    "total": 10,
}


@dataclass(frozen=True)
class SmtpConfig:
    user: str
    password: str
    sender: str
    server: str
    port: int
    from_name: str


@dataclass(frozen=True)
class EmailBranding:
    app_url: str
    logo_url: str
    banner_url: str
    privacy_url: str
    manage_url: str


# Prefixo de env por provedor. MAIL_PROVIDER=mailgun|ses seleciona o conjunto de
# credenciais; qualquer valor ausente cai no legado SMTP_* (retrocompatibilidade).
_PROVIDER_PREFIX = {"mailgun": "MAILGUN_", "ses": "SES_"}


def _resolve_provider() -> str:
    return os.getenv("MAIL_PROVIDER", "").strip().lower()


def _smtp_env(prefix: str, suffix: str, default: str = "") -> str:
    """Valor específico do provedor ({PREFIX}SMTP_{suffix}); se vazio, cai no
    legado SMTP_{suffix}."""
    value = ""
    if prefix:
        value = os.getenv(f"{prefix}SMTP_{suffix}", "").strip()
    if not value:
        value = os.getenv(f"SMTP_{suffix}", "").strip()
    return value or default


def get_smtp_config() -> SmtpConfig:
    provider = _resolve_provider()
    prefix = _PROVIDER_PREFIX.get(provider, "")

    user = _smtp_env(prefix, "USER")
    password = _smtp_env(prefix, "PASSWD")
    sender = _smtp_env(prefix, "SENDER")
    server = _smtp_env(prefix, "SERVER")
    port_raw = _smtp_env(prefix, "PORT", "587")
    from_name = _smtp_env(prefix, "FROM_NAME", "Mamute Político")

    active = f"{prefix}SMTP_*" if prefix else "SMTP_*"
    missing = [
        name
        for name, value in [
            ("USER", user),
            ("PASSWD", password),
            ("SENDER", sender),
            ("SERVER", server),
        ]
        if not value
    ]
    if missing:
        raise RuntimeError(
            f"Variáveis SMTP ausentes (provedor '{provider or 'legado'}', {active}): "
            + ", ".join(missing)
            + ". Veja mamute_scrappers/.env.example (MAIL_PROVIDER + credenciais)."
        )

    return SmtpConfig(
        user=user,
        password=password,
        sender=sender,
        server=server,
        port=int(port_raw),
        from_name=from_name,
    )


def get_branding() -> EmailBranding:
    return EmailBranding(
        app_url=os.getenv("MAMUTE_APP_URL", "https://mamutepolitico.com.br").rstrip("/"),
        logo_url=os.getenv(
            "MAMUTE_EMAIL_LOGO_URL",
            "https://mamutepolitico.com.br/app/assets/logo-mamute-Cn9vnXen.png",
        ),
        banner_url=os.getenv(
            "MAMUTE_EMAIL_BANNER_URL",
            "https://mamutepolitico.com.br/app/assets/logo-mamute-Cn9vnXen.png",
        ),
        privacy_url=os.getenv(
            "MAMUTE_PRIVACY_URL",
            "https://mamutepolitico.com.br/privacidade",
        ),
        manage_url=os.getenv(
            "MAMUTE_EMAIL_MANAGE_URL",
            "https://mamutepolitico.com.br/app",
        ),
    )


def subject_for_periodicidade(periodicidade: str) -> str:
    labels = {
        "day": "Relatório diário",
        "week": "Relatório semanal",
        "month": "Relatório mensal",
        "total": "Relatório (amostra de teste)",
    }
    return labels.get(periodicidade, "Relatório")


def default_highlight_limit(periodicidade: str) -> int:
    return DEFAULT_HIGHLIGHT_LIMIT.get(periodicidade, 9)
