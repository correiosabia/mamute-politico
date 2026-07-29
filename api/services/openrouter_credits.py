"""Monitoramento de créditos do OpenRouter (CS-31).

Em 29/07/2026 os créditos zeraram no meio da carga de embeddings e o chatbot
inteiro saiu do ar — chat e embeddings respondendo 402, sem nenhum sinal prévio.
Este módulo existe para que isso seja visível antes de acontecer.

Sobre a separação chatbot x embeddings: ela não vem pronta do provedor.
`/api/v1/activity` exige uma management key, que a chave de inferência não é.
Mas `chatbot_usage` já grava o custo real de cada consulta, então o gasto com
embeddings sai por diferença — exato no agregado, e cobre todo o histórico sem
precisar de instrumentação nova.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

import requests
from sqlalchemy import func, select
from sqlalchemy.orm import Session

try:
    from ..db.models.chatbot_usage import ChatbotUsage
except ImportError:  # execução dentro de api/
    from db.models.chatbot_usage import ChatbotUsage

logger = logging.getLogger(__name__)

CREDITS_URL = "https://openrouter.ai/api/v1/credits"
REQUEST_TIMEOUT_S = 8

# Padrões calibrados pelo incidente: a carga completa custa ~US$ 15 e o chat
# consome poucos dólares por mês. Abaixo de 10 já dá para perceber com folga;
# abaixo de 5 não cabe mais uma carga e o risco de indisponibilidade é real.
DEFAULT_ATENCAO_USD = 10.0
DEFAULT_CRITICO_USD = 5.0

# Evita bater no provedor a cada carregamento do painel.
_CACHE_TTL_S = 60
_cache: dict[str, Any] = {"em": 0.0, "valor": None}


def _threshold(nome: str, padrao: float) -> float:
    try:
        return float(os.getenv(nome, "") or padrao)
    except ValueError:
        return padrao


def fetch_credits() -> Optional[dict[str, float]]:
    """Saldo atual no OpenRouter, ou None se o provedor não responder.

    Falha suave de propósito: o painel de IA não pode cair porque o OpenRouter
    oscilou.
    """

    agora = time.monotonic()
    if _cache["valor"] is not None and agora - _cache["em"] < _CACHE_TTL_S:
        return _cache["valor"]

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        logger.warning("OPENAI_API_KEY ausente; saldo do OpenRouter indisponível.")
        return None

    try:
        resposta = requests.get(
            CREDITS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=REQUEST_TIMEOUT_S,
        )
        resposta.raise_for_status()
        dados = resposta.json().get("data") or {}
        valor = {
            "total_credits": float(dados["total_credits"]),
            "total_usage": float(dados["total_usage"]),
        }
    except (requests.RequestException, KeyError, TypeError, ValueError):
        logger.warning("Falha ao consultar créditos do OpenRouter.", exc_info=True)
        return None

    _cache.update(em=agora, valor=valor)
    return valor


def split_usage(db: Session, total_usage: float) -> dict[str, float]:
    """Reparte o gasto total entre chatbot (medido) e embeddings (por diferença)."""

    chatbot = db.execute(
        select(func.coalesce(func.sum(ChatbotUsage.cost_usd), 0)).where(
            ChatbotUsage.status == "completed"
        )
    ).scalar_one()
    chatbot = float(chatbot or 0.0)

    # Arredondamento do provedor pode deixar a diferença ligeiramente negativa.
    embeddings = max(0.0, float(total_usage) - chatbot)

    return {"chatbot_usd": chatbot, "embeddings_usd": embeddings}


def credit_status(disponivel: float, atencao: float, critico: float) -> str:
    """Classifica o saldo. Os limiares são inclusivos no pior caso."""

    if disponivel <= critico:
        return "critico"
    if disponivel < atencao:
        return "atencao"
    return "ok"


def credits_overview(db: Session) -> dict[str, Any]:
    """Payload do painel: saldo, repartição de gastos e nível de alerta."""

    atencao = _threshold("MAMUTE_CREDITS_ALERTA_USD", DEFAULT_ATENCAO_USD)
    critico = _threshold("MAMUTE_CREDITS_CRITICO_USD", DEFAULT_CRITICO_USD)

    creditos = fetch_credits()
    if creditos is None:
        return {
            "disponivel": False,
            "status": "desconhecido",
            "total_credits_usd": None,
            "total_usage_usd": None,
            "disponivel_usd": None,
            "chatbot_usd": None,
            "embeddings_usd": None,
            "limiar_atencao_usd": atencao,
            "limiar_critico_usd": critico,
        }

    disponivel_usd = creditos["total_credits"] - creditos["total_usage"]
    repartido = split_usage(db, creditos["total_usage"])

    return {
        "disponivel": True,
        "status": credit_status(disponivel_usd, atencao, critico),
        "total_credits_usd": round(creditos["total_credits"], 2),
        "total_usage_usd": round(creditos["total_usage"], 2),
        "disponivel_usd": round(disponivel_usd, 2),
        "chatbot_usd": round(repartido["chatbot_usd"], 2),
        "embeddings_usd": round(repartido["embeddings_usd"], 2),
        "limiar_atencao_usd": atencao,
        "limiar_critico_usd": critico,
    }


__all__ = [
    "fetch_credits",
    "split_usage",
    "credit_status",
    "credits_overview",
]
