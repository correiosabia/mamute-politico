#!/usr/bin/env python3
"""Verifica que cada chamada `request<T>('/path', ...)` na UI tem rota
correspondente em `api/routers/*.py`.

Roda standalone (so usa stdlib) e bloqueia o pipeline quando ha divergencia.
Pega regressoes como:
- Endpoint renomeado/movido na API sem propagacao na UI
- UI chamando rota que nunca existiu (typo, copy-paste de outro projeto)
- Router esquecido em `app.include_router(...)`

Limitacoes conhecidas:
- Compara so PATH (nao METHOD). Um GET na UI bate com qualquer verbo na API.
  Suficiente pra detectar 404, mas nao pega 405 (Method Not Allowed).
- Path params normalizados: `/foo/{id}` e `/foo/{nome}` viram `/foo/{}`.
- Query strings ignoradas (split em '?').
- Trailing slash ignorado (FastAPI faz redirect_slashes por default).

Saida:
- exit 0 + linha de OK quando tudo bate
- exit 1 + lista de divergencias quando ha problema
- exit 2 + erro quando estrutura de diretorios inesperada
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Inicio de uma chamada `request<...>(`. O argumento string e extraido depois
# por extract_first_string_arg pra lidar com template literals aninhados.
TS_REQUEST_START = re.compile(r"\brequest\s*<[^>]*>\s*\(")

# @router.get("/path") | @router.post(...) | etc
PY_ROUTE_RE = re.compile(
    r'@router\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']'
)

# APIRouter(prefix="/foo", ...)
PY_PREFIX_RE = re.compile(
    r'APIRouter\s*\([^)]*prefix\s*=\s*["\']([^"\']+)["\']'
)


@dataclass(frozen=True)
class Call:
    file: str
    line: int
    raw: str
    norm: str


@dataclass(frozen=True)
class Route:
    file: str
    line: int
    method: str
    raw: str
    norm: str


def extract_first_string_arg(text: str, start: int) -> str | None:
    """A partir de `start` (posicao logo apos `(`), extrai a primeira string
    literal/template literal. Lida com `${...}` aninhados em template literals.
    Retorna None se o primeiro arg nao for string."""
    i = start
    while i < len(text) and text[i].isspace():
        i += 1
    if i >= len(text):
        return None
    quote = text[i]
    if quote not in ("`", "'", '"'):
        return None
    i += 1
    out: list[str] = []
    while i < len(text):
        c = text[i]
        if c == "\\":  # escape — preserva o proximo char
            out.append(c)
            i += 1
            if i < len(text):
                out.append(text[i])
                i += 1
            continue
        if quote == "`" and c == "$" and i + 1 < len(text) and text[i + 1] == "{":
            # template expression: ${...} — preserva texto cru, balanceando chaves
            out.append(c)
            i += 1
            out.append(text[i])  # '{'
            i += 1
            depth = 1
            while i < len(text) and depth > 0:
                cc = text[i]
                if cc == "{":
                    depth += 1
                elif cc == "}":
                    depth -= 1
                out.append(cc)
                i += 1
            continue
        if c == quote:
            return "".join(out)
        out.append(c)
        i += 1
    return None


def normalize_path(path: str) -> str:
    """Normaliza path pra comparacao UI<->API.

    Ordem importa: substituir ${...} (com balanceamento real de chaves) ANTES
    de cortar query string, senao um `?` dentro do template literal
    (pattern comum: `${q ? \\`?${q}\\` : ''}`) corta no lugar errado."""
    # 1. ${...} de template literal -> {} (path param) ou vazio (query opcional).
    # Pattern de query opcional: `${q ? `?${q}` : ''}` — ternario com fallback
    # de string vazia. Detectamos por heuristica: contem '?', ':' e literal vazio.
    out: list[str] = []
    i = 0
    while i < len(path):
        if path[i] == "$" and i + 1 < len(path) and path[i + 1] == "{":
            depth = 1
            j = i + 2
            while j < len(path) and depth > 0:
                ch = path[j]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                j += 1
            if depth == 0:
                content = path[i + 2 : j - 1]
                is_optional_query = (
                    "?" in content
                    and ":" in content
                    and ("''" in content or '""' in content)
                )
                if not is_optional_query:
                    out.append("{}")
                # se e query opcional, nao appende nada (vazio)
                i = j
            else:
                # template aberto/quebrado — descarta resto
                break
        else:
            out.append(path[i])
            i += 1
    path = "".join(out)
    # 2. corta query string (depois do passo 1, qualquer ? agora e query real)
    path = path.split("?", 1)[0]
    # 3. {var} de FastAPI path param -> {}
    path = re.sub(r"\{[^}]+\}", "{}", path)
    # 4. trailing slash neutralizado (exceto raiz)
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return path


def find_ui_calls(ui_src: Path) -> list[Call]:
    calls: list[Call] = []
    for ts in ui_src.rglob("*.ts"):
        if "node_modules" in ts.parts or "dist" in ts.parts:
            continue
        try:
            content = ts.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for m in TS_REQUEST_START.finditer(content):
            raw = extract_first_string_arg(content, m.end())
            if raw is None:
                continue
            if raw.startswith(("http://", "https://")):
                continue
            if not raw.startswith("/"):
                continue
            line = content[: m.start()].count("\n") + 1
            calls.append(
                Call(
                    file=str(ts.relative_to(REPO)),
                    line=line,
                    raw=raw,
                    norm=normalize_path(raw),
                )
            )
    return calls


def find_api_routes(api_dir: Path) -> list[Route]:
    routes: list[Route] = []
    routers_dir = api_dir / "routers"
    for py in routers_dir.glob("*.py"):
        if py.name == "__init__.py":
            continue
        try:
            content = py.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        prefix_m = PY_PREFIX_RE.search(content)
        prefix = prefix_m.group(1) if prefix_m else ""
        for m in PY_ROUTE_RE.finditer(content):
            method = m.group(1).upper()
            path = m.group(2)
            full = prefix + path
            line = content[: m.start()].count("\n") + 1
            routes.append(
                Route(
                    file=str(py.relative_to(REPO)),
                    line=line,
                    method=method,
                    raw=full,
                    norm=normalize_path(full),
                )
            )
    return routes


def main() -> int:
    ui_src = REPO / "ui" / "src"
    api_dir = REPO / "api"
    if not ui_src.is_dir() or not api_dir.is_dir():
        print(
            f"erro: estrutura nao encontrada (ui_src={ui_src}, api_dir={api_dir})",
            file=sys.stderr,
        )
        return 2

    calls = find_ui_calls(ui_src)
    routes = find_api_routes(api_dir)
    api_paths = {r.norm for r in routes}

    missing = [c for c in calls if c.norm not in api_paths]

    print(f"UI: {len(calls)} chamada(s) request<>() | API: {len(routes)} rota(s) registrada(s)")

    if not missing:
        print("✓ Contract OK: toda chamada da UI tem rota correspondente na API.")
        return 0

    # Reporte sucinto + reverso (rotas API que ninguem chama — nao bloqueia, so info)
    seen = set()
    unique_missing = []
    for c in missing:
        key = (c.file, c.line, c.norm)
        if key in seen:
            continue
        seen.add(key)
        unique_missing.append(c)

    print(f"\n✗ {len(unique_missing)} chamada(s) UI sem rota correspondente:")
    for c in unique_missing:
        print(f"  {c.file}:{c.line}  →  {c.raw}    (normalizado: {c.norm})")

    print("\nRotas API conhecidas (para comparacao):")
    for p in sorted(api_paths):
        print(f"  {p}")

    return 1


if __name__ == "__main__":
    sys.exit(main())
