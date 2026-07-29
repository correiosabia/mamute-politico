"""Alerta de créditos baixos do OpenRouter (CS-31).

Em 29/07/2026 os créditos zeraram no meio da carga de embeddings e o chatbot
saiu do ar — chat e busca vetorial respondendo 402, sem aviso prévio nenhum.
Este job existe para que o time saiba antes, não depois.

Roda de hora em hora. O controle de repetição é essencial: sem ele, um saldo
baixo por três dias viraria 72 e-mails, o time pararia de ler, e o alerta valeria
o mesmo que nada. As regras são:

* saldo OK não gera e-mail;
* piora de estado (atenção -> crítico) avisa na hora;
* mesmo estado só repete depois de ALERT_INTERVAL_HOURS;
* melhora não gera e-mail.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

CREDITS_URL = "https://openrouter.ai/api/v1/credits"
REQUEST_TIMEOUT_S = 10

DEFAULT_ATENCAO_USD = 10.0
DEFAULT_CRITICO_USD = 5.0
DEFAULT_ALERT_INTERVAL_HOURS = 24

# Volume `scrappers_state` do compose — sobrevive a redeploy do container.
DEFAULT_STATE_PATH = Path("/app/state/openrouter_credits_alert.json")

# Ordem de gravidade, para detectar piora.
_SEVERIDADE = {"ok": 0, "atencao": 1, "critico": 2}


def _env_float(nome: str, padrao: float) -> float:
    try:
        return float(os.getenv(nome, "") or padrao)
    except ValueError:
        return padrao


def fetch_credits() -> Optional[dict[str, float]]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        logger.error("OPENAI_API_KEY ausente; não dá para checar o saldo.")
        return None
    try:
        r = requests.get(
            CREDITS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=REQUEST_TIMEOUT_S,
        )
        r.raise_for_status()
        d = r.json()["data"]
        return {
            "total_credits": float(d["total_credits"]),
            "total_usage": float(d["total_usage"]),
        }
    except (requests.RequestException, KeyError, TypeError, ValueError):
        logger.exception("Falha ao consultar créditos do OpenRouter.")
        return None


def credit_status(disponivel: float, atencao: float, critico: float) -> str:
    if disponivel <= critico:
        return "critico"
    if disponivel < atencao:
        return "atencao"
    return "ok"


def load_state(path: Path) -> Optional[dict[str, Any]]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_state(path: Path, status: str, agora: datetime) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"status": status, "enviado_em": agora.isoformat()}),
        encoding="utf-8",
    )


def should_alert(
    status: str,
    estado_anterior: Optional[dict[str, Any]],
    agora: datetime,
    intervalo_horas: int = DEFAULT_ALERT_INTERVAL_HOURS,
) -> bool:
    if status == "ok":
        return False
    if not estado_anterior:
        return True

    anterior = estado_anterior.get("status")
    if anterior not in _SEVERIDADE:
        # Estado ilegível: na dúvida, alertar. Perder aviso de saldo é pior que
        # um e-mail a mais.
        return True

    if _SEVERIDADE[status] > _SEVERIDADE[anterior]:
        return True  # piorou — é notícia nova, não espera o intervalo
    if _SEVERIDADE[status] < _SEVERIDADE[anterior]:
        return False  # melhorou

    try:
        enviado = datetime.fromisoformat(estado_anterior["enviado_em"])
    except (KeyError, TypeError, ValueError):
        return True
    if enviado.tzinfo is None:
        enviado = enviado.replace(tzinfo=timezone.utc)

    return agora - enviado >= timedelta(hours=intervalo_horas)


def admin_recipients() -> list[str]:
    bruto = os.getenv("MAMUTE_ADMIN_EMAILS", "")
    return [e.strip() for e in bruto.split(",") if e.strip()]


def build_subject(status: str) -> str:
    if status == "critico":
        return "🔴 Mamute — saldo CRÍTICO no OpenRouter"
    return "🟡 Mamute — saldo baixo no OpenRouter"


def build_alert_html(dados: dict[str, Any]) -> str:
    critico = dados["status"] == "critico"
    cor = "#c0392b" if critico else "#b45309"
    chamada = (
        "O saldo está em nível crítico. Quando zerar, <strong>o chatbot inteiro "
        "para</strong> — tanto as respostas do chat quanto a busca vetorial "
        "passam a falhar para todos os usuários."
        if critico
        else "O saldo está baixo. Vale repor antes que chegue no nível crítico, "
        "em que o chat para de responder."
    )

    return f"""
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
            max-width:560px;color:#383838;line-height:1.55">
  <h2 style="color:{cor};margin:0 0 8px">{build_subject(dados['status'])}</h2>
  <p style="margin:0 0 16px">{chamada}</p>

  <table style="border-collapse:collapse;width:100%;font-size:14px">
    <tr>
      <td style="padding:8px 0;border-bottom:1px solid #eee">Disponível</td>
      <td style="padding:8px 0;border-bottom:1px solid #eee;text-align:right;
                 font-weight:700;color:{cor}">
        US$ {dados['disponivel_usd']:.2f}
      </td>
    </tr>
    <tr>
      <td style="padding:8px 0;border-bottom:1px solid #eee">Créditos comprados</td>
      <td style="padding:8px 0;border-bottom:1px solid #eee;text-align:right">
        US$ {dados['total_credits_usd']:.2f}
      </td>
    </tr>
    <tr>
      <td style="padding:8px 0;border-bottom:1px solid #eee">Consumido — chatbot</td>
      <td style="padding:8px 0;border-bottom:1px solid #eee;text-align:right">
        US$ {dados['chatbot_usd']:.2f}
      </td>
    </tr>
    <tr>
      <td style="padding:8px 0;border-bottom:1px solid #eee">Consumido — embeddings</td>
      <td style="padding:8px 0;border-bottom:1px solid #eee;text-align:right">
        US$ {dados['embeddings_usd']:.2f}
      </td>
    </tr>
  </table>

  <p style="margin:20px 0 0">
    <a href="https://openrouter.ai/settings/credits"
       style="background:{cor};color:#fff;padding:10px 20px;border-radius:999px;
              text-decoration:none;font-weight:700;display:inline-block">
      Repor créditos no OpenRouter
    </a>
  </p>

  <p style="margin:16px 0 0;font-size:12px;color:#888">
    Limiares: atenção abaixo de US$ {dados['limiar_atencao_usd']:.2f},
    crítico em US$ {dados['limiar_critico_usd']:.2f} ou menos.
  </p>
</div>
""".strip()


def run(state_path: Path, dry_run: bool = False) -> int:
    creditos = fetch_credits()
    if creditos is None:
        print("Saldo indisponível (falha na consulta). Nada a fazer.")
        return 1

    atencao = _env_float("MAMUTE_CREDITS_ALERTA_USD", DEFAULT_ATENCAO_USD)
    critico = _env_float("MAMUTE_CREDITS_CRITICO_USD", DEFAULT_CRITICO_USD)
    intervalo = int(_env_float("MAMUTE_CREDITS_ALERTA_INTERVALO_H", DEFAULT_ALERT_INTERVAL_HOURS))

    disponivel = creditos["total_credits"] - creditos["total_usage"]
    status = credit_status(disponivel, atencao, critico)
    agora = datetime.now(timezone.utc)

    print(
        f"Saldo: US$ {disponivel:.2f} de US$ {creditos['total_credits']:.2f} "
        f"| status={status}"
    )

    anterior = load_state(state_path)
    if not should_alert(status, anterior, agora, intervalo):
        print("Sem alerta a enviar (estado OK, repetido dentro do intervalo, ou melhora).")
        return 0

    # A repartição depende do banco; importado aqui para o job não exigir DB
    # quando só está checando saldo.
    from mamute_scrappers.db.session import get_session  # type: ignore
    from sqlalchemy import text as sql_text

    with get_session() as session:
        chatbot = session.execute(
            sql_text(
                "SELECT COALESCE(SUM(cost_usd),0) FROM chatbot_usage "
                "WHERE status = 'completed'"
            )
        ).scalar() or 0
    chatbot = float(chatbot)

    dados = {
        "status": status,
        "disponivel_usd": disponivel,
        "total_credits_usd": creditos["total_credits"],
        "total_usage_usd": creditos["total_usage"],
        "chatbot_usd": chatbot,
        "embeddings_usd": max(0.0, creditos["total_usage"] - chatbot),
        "limiar_atencao_usd": atencao,
        "limiar_critico_usd": critico,
    }

    destinatarios = admin_recipients()
    if not destinatarios:
        print("AVISO: MAMUTE_ADMIN_EMAILS vazio — ninguém para avisar.")
        return 1

    html = build_alert_html(dados)
    assunto = build_subject(status)

    if dry_run:
        print(f"[dry-run] enviaria '{assunto}' para: {', '.join(destinatarios)}")
        return 0

    from mamute_scrappers.scripts.notificacao.mailer import send_html_email

    enviados = 0
    for email in destinatarios:
        try:
            send_html_email(html, email, assunto)
            enviados += 1
        except Exception:  # noqa: BLE001 - um destinatário ruim não trava os outros
            logger.exception("Falha ao enviar alerta para %s", email)

    if enviados:
        save_state(state_path, status, agora)
        print(f"Alerta '{status}' enviado para {enviados} admin(s).")
        return 0

    print("Nenhum alerta enviado (todas as tentativas falharam).")
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Alerta admins quando o saldo do OpenRouter fica baixo."
    )
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    raise SystemExit(run(args.state, args.dry_run))


if __name__ == "__main__":
    main()
