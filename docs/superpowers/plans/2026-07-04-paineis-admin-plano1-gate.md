# Painéis Admin — Plano 1 (Gate) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Criar o gate server-side de admin (allowlist de e-mail + feature flag) e uma rota `/api/admin/whoami` protegida, mais o shell de `/admin` no front — validando o controle de acesso ponta a ponta antes de qualquer painel real.

**Architecture:** A checagem "é admin?" fica **inteira numa função** (`require_ghost_admin`) em `api/security.py`, reusando a validação de JWT Ghost já existente. Não-admin, sem token ou flag desligada → **404** (esconde a existência da superfície). O front tem um `RequireAdmin` que só renderiza `/admin` se o backend confirmar; esconder a aba é só UX. Este plano **não toca banco** — `whoami` só lê o token.

**Tech Stack:** FastAPI + PyJWT (backend), React 18 + React Router 6 + TanStack Query + shadcn/ui (front), pytest (testes de backend).

## Global Constraints

- Home de todas as rotas admin: **`api/`**, sob o prefixo final `/api/admin/*`. (spec §2)
- Resposta para não-admin / flag off: **HTTP 404** no router `/admin` inteiro — nunca 401/403 nessas rotas, para não vazar a existência. (spec §2, §4.1)
- Identificação de admin: **allowlist de e-mails via env** `MAMUTE_ADMIN_EMAILS` (lista separada por vírgula), comparada ao claim `sub` (e-mail) do JWT Ghost, normalizado para lowercase. (spec §2)
- Feature flag: env **`MAMUTE_ADMIN_PANELS_ENABLED`** (default `false`). (spec §2)
- Toda a lógica "é admin?" vive numa **única função** (`require_ghost_admin`) para troca futura por Ghost Admin API sem tocar rotas. (spec §4.1)
- Enforcement é **100% server-side**; esconder a aba no front é apenas UX. (spec §1)

---

### Task 1: Gate de admin em `api/security.py`

Refatora `verify_token` para extrair o decode do JWT num helper reusável, adiciona `get_admin_settings()` (lê env) e a dependency `require_ghost_admin` (o gate 404).

**Files:**
- Modify: `api/security.py`
- Test: `api/tests/test_admin_gate.py` (create)

**Interfaces:**
- Consumes: `get_ghost_settings()`, `get_public_key()`, `_extract_token()`, `JWT_ALGORITHM` (já existentes em `api/security.py`).
- Produces:
  - `get_admin_settings() -> Dict[str, Any]` → `{"enabled": bool, "emails": frozenset[str]}`
  - `require_ghost_admin(request: Request, authorization: str | None = Header(default=None)) -> str` → retorna o e-mail admin (lowercase) ou levanta `HTTPException(404)`.
  - `_decode_ghost_jwt(token: str) -> Dict[str, Any]` → decode + retry de rotação de chave (helper interno, também usado por `verify_token`).

- [ ] **Step 1: Write the failing tests**

Create `api/tests/test_admin_gate.py`:

```python
"""Testes do gate de admin (require_ghost_admin).

O gate deve devolver 404 para TUDO que nao seja admin autenticado com a
feature flag ligada — sem vazar a existencia da superficie /admin.
"""
from __future__ import annotations

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> TestClient:
    from api.main import app

    return TestClient(app)


def _fake_decode(payload: dict):
    def _decode(_token: str) -> dict:
        return payload

    return _decode


def test_admin_ok(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from api import security

    monkeypatch.setenv("MAMUTE_ADMIN_PANELS_ENABLED", "true")
    monkeypatch.setenv("MAMUTE_ADMIN_EMAILS", "admin@x.com, other@x.com")
    monkeypatch.setattr(security, "_decode_ghost_jwt", _fake_decode({"sub": "Admin@X.com"}))

    resp = client.get("/api/admin/whoami", headers={"Authorization": "Bearer faketoken"})

    assert resp.status_code == 200
    assert resp.json() == {"email": "admin@x.com", "is_admin": True}


def test_flag_off_is_404_even_for_admin(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from api import security

    monkeypatch.setenv("MAMUTE_ADMIN_PANELS_ENABLED", "false")
    monkeypatch.setenv("MAMUTE_ADMIN_EMAILS", "admin@x.com")
    monkeypatch.setattr(security, "_decode_ghost_jwt", _fake_decode({"sub": "admin@x.com"}))

    resp = client.get("/api/admin/whoami", headers={"Authorization": "Bearer faketoken"})

    assert resp.status_code == 404


def test_non_admin_email_is_404(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from api import security

    monkeypatch.setenv("MAMUTE_ADMIN_PANELS_ENABLED", "true")
    monkeypatch.setenv("MAMUTE_ADMIN_EMAILS", "admin@x.com")
    monkeypatch.setattr(security, "_decode_ghost_jwt", _fake_decode({"sub": "rando@x.com"}))

    resp = client.get("/api/admin/whoami", headers={"Authorization": "Bearer faketoken"})

    assert resp.status_code == 404


def test_no_token_is_404(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAMUTE_ADMIN_PANELS_ENABLED", "true")
    monkeypatch.setenv("MAMUTE_ADMIN_EMAILS", "admin@x.com")

    resp = client.get("/api/admin/whoami")

    assert resp.status_code == 404


def test_invalid_token_is_404(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from api import security

    def _boom(_token: str) -> dict:
        raise pyjwt.InvalidTokenError("bad")

    monkeypatch.setenv("MAMUTE_ADMIN_PANELS_ENABLED", "true")
    monkeypatch.setenv("MAMUTE_ADMIN_EMAILS", "admin@x.com")
    monkeypatch.setattr(security, "_decode_ghost_jwt", _boom)

    resp = client.get("/api/admin/whoami", headers={"Authorization": "Bearer faketoken"})

    assert resp.status_code == 404
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/luiz/dev/correio-sabia/mamute-politico && python -m pytest api/tests/test_admin_gate.py -v`
Expected: FAIL — `/api/admin/whoami` ainda não existe (404 por rota inexistente ou ImportError de `require_ghost_admin`). Nesta fase o teste `test_admin_ok` falha (não retorna 200), confirmando que a rota/gate não existe.

- [ ] **Step 3: Refatorar o decode para um helper e adicionar o gate**

Em `api/security.py`, adicione `Any` já está importado. Após a função `_extract_token` (linha ~85), **substitua** a função `verify_token` inteira (linhas 88-122) por este bloco (helper + verify_token refatorado + settings + gate):

```python
def _decode_ghost_jwt(token: str) -> Dict[str, Any]:
    """Decodifica o JWT Ghost, com um retry em caso de rotação de chave."""
    settings = get_ghost_settings()
    public_key = get_public_key()
    try:
        return jwt.decode(
            token,
            public_key,
            algorithms=[JWT_ALGORITHM],
            audience=settings["audience"],
            issuer=settings["issuer"],
        )
    except InvalidSignatureError:
        # Possível rotação de chave: limpa o cache e tenta novamente uma vez.
        get_public_key.cache_clear()  # type: ignore[attr-defined]
        public_key = get_public_key()
        return jwt.decode(
            token,
            public_key,
            algorithms=[JWT_ALGORITHM],
            audience=settings["audience"],
            issuer=settings["issuer"],
        )


def verify_token(request: Request, authorization: str = Header(...)) -> Dict[str, Any]:
    """Valida o JWT emitido pelo Ghost Members."""
    token = _extract_token(authorization)
    try:
        decoded_token = _decode_ghost_jwt(token)
    except ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="O token expirou.") from exc
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="O token é inválido.") from exc

    # Armazena informações úteis para acesso nas rotas.
    request.state.token_payload = decoded_token
    request.state.token_email = decoded_token.get("sub")

    return decoded_token


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def get_admin_settings() -> Dict[str, Any]:
    """Lê a config do gate admin do ambiente (sem cache: barato e testável)."""
    raw = os.getenv("MAMUTE_ADMIN_EMAILS", "")
    emails = frozenset(e.strip().lower() for e in raw.split(",") if e.strip())
    return {"enabled": _env_flag("MAMUTE_ADMIN_PANELS_ENABLED"), "emails": emails}


def require_ghost_admin(
    request: Request, authorization: str | None = Header(default=None)
) -> str:
    """Gate único de admin. Qualquer falha vira 404 (esconde a superfície)."""
    cfg = get_admin_settings()
    not_found = HTTPException(status_code=404, detail="Not Found")

    if not cfg["enabled"] or not authorization:
        raise not_found

    try:
        token = _extract_token(authorization)
        decoded = _decode_ghost_jwt(token)
    except HTTPException:
        raise not_found
    except Exception:  # noqa: BLE001 — qualquer erro de token vira 404
        raise not_found

    email = (decoded.get("sub") or "").strip().lower()
    if not email or email not in cfg["emails"]:
        raise not_found

    request.state.token_payload = decoded
    request.state.token_email = email
    request.state.is_admin = True
    return email
```

Em seguida, atualize o `__all__` no fim do arquivo:

```python
__all__ = [
    "verify_token",
    "get_ghost_settings",
    "get_public_key",
    "get_admin_settings",
    "require_ghost_admin",
]
```

- [ ] **Step 4: Adicionar o router e a rota (necessário para os testes passarem)**

Este passo é a Task 2, mas os testes da Task 1 dependem da rota existir. Implemente a Task 2 (Steps abaixo) e volte a rodar. **Não commite ainda.**

- [ ] **Step 5: Rodar os testes do gate**

Run: `python -m pytest api/tests/test_admin_gate.py -v`
Expected: PASS (5 passed) — só depois da Task 2 estar aplicada.

- [ ] **Step 6: Commit** (junto com a Task 2)

---

### Task 2: Router `/admin` + `whoami` + wiring no app

**Files:**
- Create: `api/routers/admin.py`
- Modify: `api/main.py` (importar e registrar o router admin — nos DOIS blocos try/except)
- Modify: `api/tests/test_smoke.py` (incluir `admin` na lista de routers importáveis)

**Interfaces:**
- Consumes: `require_ghost_admin` (Task 1).
- Produces: `router` (APIRouter, `prefix="/admin"`); rota `GET /api/admin/whoami` → `{"email": str, "is_admin": true}`.

- [ ] **Step 1: Criar o router admin**

Create `api/routers/admin.py`:

```python
"""Rotas administrativas — gated por require_ghost_admin (404 para não-admin)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

try:
    from ..security import require_ghost_admin
except ImportError:  # execução dentro de api/
    from security import require_ghost_admin

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/whoami")
def whoami(admin_email: str = Depends(require_ghost_admin)) -> dict:
    """Valida o gate ponta a ponta: só admin autenticado chega aqui."""
    return {"email": admin_email, "is_admin": True}
```

- [ ] **Step 2: Registrar o router em `api/main.py`**

No bloco `try` (imports como pacote), adicione `admin` à tupla de import dos routers (após `from .routers import (` ... adicionar `admin,`) e no bloco `except ImportError` idem (`from routers import (` ... `admin,`). Depois, em `create_app()`, registre o router admin **sem** `auth_dependencies` (ele tem o próprio gate). Adicione, logo após `api_router.include_router(ghost_webhooks.router)` (linha ~60):

```python
    api_router.include_router(admin.router)
```

O import no bloco `try` fica:

```python
    from .routers import (
        admin,
        analysis,
        authors_proposition,
        ghost_webhooks,
        projects,
        parliamentarians,
        propositions,
        roll_call_votes,
        speeches_transcripts,
        speeches_transcripts_proposition,
    )
```

E igual no bloco `except ImportError` (trocando `.routers` por `routers`).

- [ ] **Step 3: Atualizar o smoke test**

Em `api/tests/test_smoke.py`, na função `test_all_routers_importable`, adicione `"admin",` no início da lista `routers` (linha ~33).

- [ ] **Step 4: Rodar o smoke + gate + suíte da api**

Run: `python -m pytest api/tests/test_smoke.py api/tests/test_admin_gate.py -v`
Expected: PASS (todos). O `test_admin_ok` agora retorna 200; os demais 404.

- [ ] **Step 5: Rodar a suíte inteira da api (regressão)**

Run: `python -m pytest api/tests/ -q`
Expected: PASS — nenhuma regressão em `verify_token` (o refactor preserva o comportamento).

- [ ] **Step 6: Commit**

```bash
git add api/security.py api/routers/admin.py api/main.py api/tests/test_admin_gate.py api/tests/test_smoke.py
git commit -m "feat(admin): gate server-side (allowlist + flag) e rota /admin/whoami"
```

---

### Task 3: Front — `RequireAdmin`, rota `/admin` e aba condicional

**Files:**
- Create: `ui/src/api/admin.ts`
- Create: `ui/src/hooks/useIsAdmin.ts`
- Create: `ui/src/pages/AdminPage.tsx`
- Modify: `ui/src/App.tsx` (adicionar `RequireAdmin` + rota `/admin`)
- Modify: `ui/src/components/layout/Header.tsx` (link condicional para `/admin`)

**Interfaces:**
- Consumes: `request` (`ui/src/api/client.ts`), `useGhostAuth` (`ui/src/components/auth/ghost-auth/react/useGhostAuth`).
- Produces:
  - `fetchWhoami(): Promise<WhoamiResponse>` onde `WhoamiResponse = { email: string; is_admin: boolean }`.
  - `useIsAdmin(): { isAdmin: boolean; isLoading: boolean }`.

- [ ] **Step 1: Criar o client admin**

Create `ui/src/api/admin.ts`:

```ts
import { request } from './client';

export interface WhoamiResponse {
  email: string;
  is_admin: boolean;
}

/** Confirma no backend se o membro logado é admin. 404 = não admin. */
export function fetchWhoami(): Promise<WhoamiResponse> {
  return request<WhoamiResponse>('/admin/whoami');
}
```

- [ ] **Step 2: Criar o hook `useIsAdmin`**

Create `ui/src/hooks/useIsAdmin.ts`:

```ts
import { useQuery } from '@tanstack/react-query';
import { fetchWhoami } from '@/api/admin';
import { useGhostAuth } from '@/components/auth/ghost-auth/react/useGhostAuth';

/** Deriva status de admin do backend. 404/erro => não admin. */
export function useIsAdmin(): { isAdmin: boolean; isLoading: boolean } {
  const token = useGhostAuth();
  const query = useQuery({
    queryKey: ['admin', 'whoami'],
    queryFn: fetchWhoami,
    enabled: Boolean(token),
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

  return {
    isAdmin: query.data?.is_admin === true,
    isLoading: Boolean(token) && query.isLoading,
  };
}
```

- [ ] **Step 3: Criar a página placeholder**

Create `ui/src/pages/AdminPage.tsx`:

```tsx
import { useIsAdmin } from '@/hooks/useIsAdmin';

export default function AdminPage() {
  const { isAdmin } = useIsAdmin();

  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="text-2xl font-semibold">Painel administrativo</h1>
      <p className="mt-4 text-muted-foreground">
        Acesso confirmado{isAdmin ? '' : '?'}. Painéis de gestão e métricas serão
        adicionados aqui.
      </p>
    </main>
  );
}
```

- [ ] **Step 4: Adicionar `RequireAdmin` e a rota em `ui/src/App.tsx`**

Adicione o import (junto aos outros de página, linha ~12):

```tsx
import AdminPage from "./pages/AdminPage";
import { useIsAdmin } from "@/hooks/useIsAdmin";
```

Adicione o componente `RequireAdmin` logo após `RequireAuth` (linha ~78):

```tsx
function RequireAdmin({ children }: { children: JSX.Element }) {
  const token = useGhostAuth();
  const { isAdmin, isLoading } = useIsAdmin();

  if (!token) {
    return <Navigate to="/" replace />;
  }
  if (isLoading) {
    return null;
  }
  if (!isAdmin) {
    return <Navigate to="/" replace />;
  }
  return children;
}
```

Adicione a rota **acima** do catch-all `"*"` (linha ~122):

```tsx
              <Route
                path="/admin"
                element={
                  <RequireAdmin>
                    <AdminPage />
                  </RequireAdmin>
                }
              />
```

- [ ] **Step 5: Link condicional no Header**

Em `ui/src/components/layout/Header.tsx`, importe o hook e a `Link` do react-router (se ainda não importada) e renderize um link para `/admin` **apenas** quando `isAdmin`. Adicione perto dos demais itens de navegação:

```tsx
import { useIsAdmin } from '@/hooks/useIsAdmin';
// ...dentro do componente Header:
const { isAdmin } = useIsAdmin();
// ...no JSX de navegação, junto aos outros links:
{isAdmin && (
  <Link to="/admin" className="text-sm font-medium hover:underline">
    Admin
  </Link>
)}
```

(Se o `Header` não usar `Link` do `react-router-dom`, siga o padrão de navegação já presente no arquivo — o ponto é: renderizar só quando `isAdmin`.)

- [ ] **Step 6: Verificar build/typecheck do front**

Run: `cd ui && npm run build`
Expected: build sem erros de TypeScript.

- [ ] **Step 7: Commit**

```bash
cd /Users/luiz/dev/correio-sabia/mamute-politico
git add ui/src/api/admin.ts ui/src/hooks/useIsAdmin.ts ui/src/pages/AdminPage.tsx ui/src/App.tsx ui/src/components/layout/Header.tsx
git commit -m "feat(admin): RequireAdmin, rota /admin e aba condicional no front"
```

---

### Task 4: Validação local ponta a ponta (antes de qualquer PR)

Objetivo: você ver o gate funcionando na sua máquina. Sem migration (Plano 1 não toca DB).

**Files:** nenhum (configuração + verificação manual).

- [ ] **Step 1: Configurar env local da api**

No `.env` da `api/` (local), garanta:
- `GHOST_BASE_URL` = URL do Ghost (o mesmo de prod, para validar JWT real).
- `DATABASE_URL` = Postgres local/prod acessível.
- `MAMUTE_ADMIN_PANELS_ENABLED=true`
- `MAMUTE_ADMIN_EMAILS=luizvi99@gmail.com` (o e-mail da sua conta Ghost)

- [ ] **Step 2: Subir api + ui local**

Rodar backend e frontend no loop de dev (uvicorn --reload + vite) ou via docker compose do projeto. (O executor confirma o comando exato do projeto ao subir.)

- [ ] **Step 3: Checklist de validação (manual)**

- [ ] Logar na UI com a conta Ghost cujo e-mail está na allowlist → aba **Admin** aparece; abrir `/admin` mostra "Painel administrativo".
- [ ] `GET /api/admin/whoami` com o Bearer desse login → `200 {"email": "...", "is_admin": true}`.
- [ ] Remover o e-mail da allowlist (ou logar com outra conta) e reiniciar api → `/api/admin/whoami` retorna **404** e a aba **some**.
- [ ] `MAMUTE_ADMIN_PANELS_ENABLED=false` e reiniciar → `/api/admin/whoami` retorna **404 mesmo para o admin**.
- [ ] `GET /api/admin/whoami` sem header Authorization → **404**.

- [ ] **Step 4: Sinalizar pro Luiz revisar**

Só depois do checklist verde, seguir para PR (ou para o Plano 2).

---

## Self-Review

**Spec coverage (Plano 1 — spec §5):** gate 404 ✔ (Task 1), feature flag ✔ (Task 1), allowlist env ✔ (Task 1), lógica isolada numa função ✔ (`require_ghost_admin`), `whoami` ponta a ponta ✔ (Task 2), front `RequireAdmin` + aba condicional ✔ (Task 3), enforcement server-side testado ✔ (test_admin_gate). **Desvio consciente:** a tabela `admin_audit_log` (listada no spec §5 Plano 1) foi movida para o **Plano 2**, onde é de fato escrita — Plano 1 não persiste nada (YAGNI). Registrar essa mudança ao atualizar o spec.

**Placeholder scan:** sem TBD/TODO; todo passo tem código real.

**Type consistency:** `require_ghost_admin` retorna `str` (email) e é o `Depends` de `whoami` (`admin_email: str`). `WhoamiResponse`/`fetchWhoami`/`useIsAdmin` consistentes entre front (`is_admin: boolean`) e backend (`{"is_admin": True}`). `_decode_ghost_jwt` usado por `verify_token` e `require_ghost_admin`.
