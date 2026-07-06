"""Agregações para o painel de métricas admin.

Custo/margem são computados em Python (lendo tier.detalhes) para evitar
diferenças de acesso a JSON entre PostgreSQL e SQLite (usado nos testes).
"""
from __future__ import annotations

import logging
import os
import time
from datetime import date
from typing import Any, Optional

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

logger = logging.getLogger("admin_metrics")

_PAGE_LABELS = {
    "inicio": "Início",
    "dashboard": "Dashboard Geral",
    "selecao": "Selecionar Parlamentares",
    "pesquisa": "Pesquisa IA (visitas)",
    "parlamentar": "Página de Parlamentar",
}


def _page_label(page: Optional[str]) -> str:
    return _PAGE_LABELS.get(page or "", page or "—")


def _house_of(ptype: Optional[str]) -> str:
    return "senado" if ptype and "senad" in ptype.lower() else "camara"

_USD_BRL_URL = "https://economia.awesomeapi.com.br/last/USD-BRL"
_RATE_TTL_SECONDS = 1800
_rate_cache: dict[str, Any] = {"value": None, "at": 0.0}
# Emergência de cold-start APENAS: sem env, sem linha em usd_brl_rate e API fora.
# Em regime a taxa vem da tabela usd_brl_rate (real, atualizada 1x/dia às 04h
# por mamute_scrappers.scripts.refresh_admin_caches). Sem valor fixo "de fachada".
_COLD_START_USD_BRL = 6.0


def _fetch_live_usd_brl() -> Optional[float]:
    try:
        import requests

        resp = requests.get(_USD_BRL_URL, timeout=4)
        resp.raise_for_status()
        return float(resp.json()["USDBRL"]["bid"])
    except Exception:  # noqa: BLE001 — câmbio nunca pode quebrar as métricas
        return None


def _latest_rate_from_db(db: Optional[Session]) -> Optional[float]:
    if db is None:
        return None
    try:
        row = db.execute(
            text("SELECT bid FROM usd_brl_rate ORDER BY rate_date DESC LIMIT 1")
        ).first()
    except Exception:  # noqa: BLE001 — tabela ausente (migration/testes) → ignora
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None
    return float(row[0]) if row and row[0] is not None else None


def get_usd_brl_rate(db: Optional[Session] = None) -> float:
    """Taxa USD→BRL real do dia.

    Ordem: env (pin p/ testes) → cache em memória (30min) → tabela usd_brl_rate
    (fonte da verdade, preenchida diariamente) → busca ao vivo (bootstrap) →
    último valor conhecido. Sem fallback fixo desatualizado no caminho normal.
    """
    override = os.getenv("MAMUTE_USD_BRL_RATE")
    if override:
        try:
            return float(override)
        except ValueError:
            pass

    now = time.time()
    cached = _rate_cache["value"]
    if cached is not None and now - _rate_cache["at"] < _RATE_TTL_SECONDS:
        return float(cached)

    rate = _latest_rate_from_db(db)
    if rate is None:
        rate = _fetch_live_usd_brl()
    if rate is None:
        # Sem banco nem rede: usa o último valor conhecido em memória; se não há
        # nenhum (cold start absoluto), emergência logada — some no 1º ciclo.
        if cached is not None:
            return float(cached)
        logger.warning(
            "Câmbio USD→BRL indisponível (sem env/tabela/rede); usando cold-start %.2f",
            _COLD_START_USD_BRL,
        )
        return _COLD_START_USD_BRL

    _rate_cache["value"] = rate
    _rate_cache["at"] = now
    return rate

try:
    from ..db.models.project import Projetos, ProjetosParliamentarian
    from ..db.models.chatbot_usage import ChatbotUsage
    from ..db.models.usage_event import UsageEvent
except ImportError:  # execução dentro de api/
    from db.models.project import Projetos, ProjetosParliamentarian
    from db.models.chatbot_usage import ChatbotUsage
    from db.models.usage_event import UsageEvent


def current_period_start(today: Optional[date] = None) -> date:
    """Primeiro dia do mês atual (mesma convenção de chatbot_usage.period_start)."""
    ref = today or date.today()
    return ref.replace(day=1)


def _usage_by_project(db: Session, period_start: Optional[date]) -> dict[int, Any]:
    tokens = func.coalesce(ChatbotUsage.prompt_tokens, 0) + func.coalesce(
        ChatbotUsage.completion_tokens, 0
    )
    stmt = (
        select(
            ChatbotUsage.projeto_id.label("projeto_id"),
            func.count().label("calls"),
            func.coalesce(func.sum(tokens), 0).label("tokens"),
            func.coalesce(func.sum(ChatbotUsage.cost_usd), 0).label("cost"),
        )
        .where(ChatbotUsage.status == "completed")
        .group_by(ChatbotUsage.projeto_id)
    )
    if period_start is not None:
        stmt = stmt.where(ChatbotUsage.period_start == period_start)
    return {row.projeto_id: row for row in db.execute(stmt)}


def _favorites_by_project(db: Session) -> dict[int, int]:
    stmt = (
        select(
            ProjetosParliamentarian.projeto_id.label("projeto_id"),
            func.count().label("n"),
        )
        .where(ProjetosParliamentarian.deleted_at.is_(None))
        .group_by(ProjetosParliamentarian.projeto_id)
    )
    return {row.projeto_id: int(row.n) for row in db.execute(stmt)}


def metrics_users(
    db: Session,
    period_start: date,
    usd_brl_rate: float,
    *,
    limit: Optional[int] = None,
    search: Optional[str] = None,
) -> list[dict[str, Any]]:
    query = select(Projetos).where(Projetos.deleted_at.is_(None))
    if search:
        like = f"%{search.strip()}%"
        query = query.where(Projetos.nome.ilike(like) | Projetos.email.ilike(like))
    projetos = db.execute(query).scalars().all()
    month = _usage_by_project(db, period_start)
    total = _usage_by_project(db, None)
    favorites = _favorites_by_project(db)

    users: list[dict[str, Any]] = []
    for projeto in projetos:
        detalhes = (getattr(projeto.tier, "detalhes", None) or {}) if projeto.tier else {}
        preco = float(detalhes.get("preco_mensal") or 0)
        month_row = month.get(projeto.id)
        total_row = total.get(projeto.id)
        custo_mes = float(month_row.cost) if month_row else 0.0
        custo_mes_brl = custo_mes * usd_brl_rate
        consultas_mes = int(month_row.calls) if month_row else 0
        limite_consultas = detalhes.get("qtd_consultas_ia_mes")
        limite_parlamentares = detalhes.get("qtd_termos")
        monitorados = favorites.get(projeto.id, 0)

        users.append(
            {
                "projeto_id": projeto.id,
                "email": projeto.email,
                "nome": projeto.nome,
                "plano": projeto.tier.product_id if projeto.tier else None,
                "preco_mensal": round(preco, 2),
                "consultas_mes": consultas_mes,
                "consultas_total": int(total_row.calls) if total_row else 0,
                "tokens_mes": int(month_row.tokens) if month_row else 0,
                "custo_mes": round(custo_mes, 6),
                "custo_mes_brl": round(custo_mes_brl, 2),
                "margem_mes": round(preco - custo_mes_brl, 2),
                "parlamentares_monitorados": monitorados,
                "limite_parlamentares": limite_parlamentares,
                "limite_consultas": limite_consultas,
                # Acima do plano = estourou IA/mês OU parlamentares monitorados.
                "acima_do_plano": bool(
                    (limite_consultas is not None and consultas_mes > int(limite_consultas))
                    or (
                        limite_parlamentares is not None
                        and monitorados > int(limite_parlamentares)
                    )
                ),
            }
        )

    users.sort(key=lambda u: u["custo_mes"], reverse=True)
    if limit is not None:
        return users[:limit]
    return users


def _ia_by_day(
    db: Session, projeto_id: Optional[int], usd_brl_rate: float
) -> list[dict[str, Any]]:
    dia = func.date(ChatbotUsage.created_at)
    stmt = (
        select(
            dia.label("dia"),
            func.count().label("consultas"),
            func.coalesce(func.sum(ChatbotUsage.cost_usd), 0).label("custo"),
        )
        .where(ChatbotUsage.status == "completed")
        .group_by(dia)
        .order_by(dia)
    )
    if projeto_id is not None:
        stmt = stmt.where(ChatbotUsage.projeto_id == projeto_id)
    return [
        {
            "dia": str(row.dia),
            "consultas": int(row.consultas),
            "custo_brl": round(float(row.custo) * usd_brl_rate, 2),
        }
        for row in db.execute(stmt)
    ]


def _pages_by_project(db: Session, projeto_id: int) -> list[dict[str, Any]]:
    stmt = (
        select(UsageEvent.page.label("page"), func.count().label("views"))
        .where(
            UsageEvent.projeto_id == projeto_id,
            UsageEvent.event_type == "page_view",
        )
        .group_by(UsageEvent.page)
        .order_by(func.count().desc())
    )
    return [
        {"page": row.page or "—", "views": int(row.views)} for row in db.execute(stmt)
    ]


def _swaps_by_project(db: Session, projeto_id: int) -> dict[str, int]:
    stmt = (
        select(UsageEvent.event_type.label("etype"), func.count().label("cnt"))
        .where(
            UsageEvent.projeto_id == projeto_id,
            UsageEvent.event_type.in_(["favorite_added", "favorite_removed"]),
        )
        .group_by(UsageEvent.event_type)
    )
    counts = {row.etype: int(row.cnt) for row in db.execute(stmt)}
    adicionados = counts.get("favorite_added", 0)
    removidos = counts.get("favorite_removed", 0)
    return {"adicionados": adicionados, "removidos": removidos, "total": adicionados + removidos}


def metrics_user_detail(
    db: Session, projeto_id: int, period_start: date, usd_brl_rate: float
) -> Optional[dict[str, Any]]:
    base = next(
        (
            u
            for u in metrics_users(db, period_start, usd_brl_rate)
            if u["projeto_id"] == projeto_id
        ),
        None,
    )
    if base is None:
        return None
    return {
        **base,
        "ia_por_dia": _ia_by_day(db, projeto_id, usd_brl_rate),
        "paginas": _pages_by_project(db, projeto_id),
        "trocas": _swaps_by_project(db, projeto_id),
    }


def metrics_tools(db: Session) -> list[dict[str, Any]]:
    """Ferramentas mais usadas: page views + consultas IA + trocas de monitoramento."""
    tools: list[dict[str, Any]] = []

    page_rows = (
        db.execute(
            select(UsageEvent.page.label("page"), func.count().label("n"))
            .where(UsageEvent.event_type == "page_view")
            .group_by(UsageEvent.page)
        )
        .all()
    )
    for row in page_rows:
        if row.page:
            tools.append({"tool": _page_label(row.page), "uses": int(row.n)})

    ia_calls = db.execute(
        select(func.count()).where(ChatbotUsage.status == "completed")
    ).scalar_one()
    tools.append({"tool": "Pesquisa IA (consultas)", "uses": int(ia_calls or 0)})

    trocas = db.execute(
        select(func.count()).where(
            UsageEvent.event_type.in_(["favorite_added", "favorite_removed"])
        )
    ).scalar_one()
    tools.append({"tool": "Monitoramento (trocas)", "uses": int(trocas or 0)})

    tools.sort(key=lambda t: t["uses"], reverse=True)
    return tools


def metrics_sections(db: Session) -> list[dict[str, Any]]:
    """Seções mais vistas dentro das telas (event_type='section_view')."""
    stmt = (
        select(
            UsageEvent.page.label("page"),
            UsageEvent.section.label("section"),
            func.count().label("views"),
        )
        .where(UsageEvent.event_type == "section_view")
        .group_by(UsageEvent.page, UsageEvent.section)
        .order_by(func.count().desc())
    )
    return [
        {
            "page": _page_label(row.page),
            "section": row.section or "—",
            "views": int(row.views),
        }
        for row in db.execute(stmt)
    ]


def metrics_parliamentarians(db: Session, limit: int = 20) -> dict[str, Any]:
    """Parlamentares mais monitorados, separando Câmara/Senado e por estado."""
    rows = (
        db.execute(
            text(
                """
                SELECT p.id AS pid, p.name AS name, p.type AS ptype,
                       COALESCE(p.state_elected, '') AS state, COUNT(*) AS monitors
                FROM projetos_parliamentarian pp
                JOIN parliamentarian p ON p.id = pp.parliamentarian_id
                WHERE pp.deleted_at IS NULL
                GROUP BY p.id, p.name, p.type, p.state_elected
                ORDER BY monitors DESC
                """
            )
        )
        .mappings()
        .all()
    )

    top: list[dict[str, Any]] = []
    by_house = {"camara": 0, "senado": 0}
    by_state: dict[str, int] = {}
    for row in rows:
        house = _house_of(row["ptype"])
        monitors = int(row["monitors"])
        by_house[house] += monitors
        state = row["state"] or "?"
        by_state[state] = by_state.get(state, 0) + monitors
        top.append(
            {
                "parliamentarian_id": row["pid"],
                "name": row["name"],
                "house": house,
                "state": state,
                "monitors": monitors,
            }
        )

    by_state_list = sorted(
        ({"state": s, "monitors": n} for s, n in by_state.items()),
        key=lambda x: x["monitors"],
        reverse=True,
    )
    return {"top": top[:limit], "by_house": by_house, "by_state": by_state_list}


def metrics_ia(db: Session, period_start: date, usd_brl_rate: float) -> dict[str, Any]:
    """Métricas focadas em IA: volume, tokens, custo, top usuários, série diária."""
    usage = _usage_by_project(db, period_start)
    consultas = sum(int(r.calls) for r in usage.values())
    tokens = sum(int(r.tokens) for r in usage.values())
    custo_usd = sum(float(r.cost) for r in usage.values())

    users = metrics_users(db, period_start, usd_brl_rate)
    top = sorted(users, key=lambda u: u["custo_mes"], reverse=True)[:10]
    return {
        "consultas_mes": consultas,
        "tokens_mes": tokens,
        "custo_mes_brl": round(custo_usd * usd_brl_rate, 2),
        "usd_brl_rate": round(usd_brl_rate, 4),
        "por_dia": _ia_by_day(db, None, usd_brl_rate),
        "top_usuarios": [
            {
                "projeto_id": u["projeto_id"],
                "email": u["email"],
                "nome": u["nome"],
                "consultas_mes": u["consultas_mes"],
                "custo_mes_brl": u["custo_mes_brl"],
            }
            for u in top
        ],
    }


def metrics_overview(
    db: Session, period_start: date, usd_brl_rate: float
) -> dict[str, Any]:
    users = metrics_users(db, period_start, usd_brl_rate)
    receita = sum(u["preco_mensal"] for u in users)
    custo_usd = sum(u["custo_mes"] for u in users)
    custo_brl = sum(u["custo_mes_brl"] for u in users)
    return {
        "usuarios": len(users),
        "consultas_mes": sum(u["consultas_mes"] for u in users),
        "tokens_mes": sum(u["tokens_mes"] for u in users),
        "custo_mes": round(custo_usd, 6),
        "custo_mes_brl": round(custo_brl, 2),
        "receita_mes": round(receita, 2),
        "margem_mes": round(receita - custo_brl, 2),
        "usd_brl_rate": round(usd_brl_rate, 4),
        "parlamentares_monitorados": sum(u["parlamentares_monitorados"] for u in users),
        "usuarios_acima_do_plano": sum(1 for u in users if u["acima_do_plano"]),
    }
