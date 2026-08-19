# Cota Parlamentar (CS-57) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Coletar, armazenar e expor os gastos da cota parlamentar (CEAP Câmara + CEAPS Senado) por mês, tipo e fornecedor, com link para o documento fiscal, atrás da flag `cota_parlamentar`.

**Architecture:** Tabela única `parliamentary_expense` com discriminador `house` e chave natural `(house, source_key)`; dois crawlers (CSV anual da Câmara, API JSON do Senado) casando por `parliamentarian_code` sem fuzzy; agregação on-the-fly no router `/expenses`; aba GASTOS no perfil com gráfico mensal empilhado.

**Tech Stack:** SQLAlchemy + Alembic, FastAPI + Pydantic, requests, React + TanStack Query + recharts + shadcn/ui, pytest + vitest.

**Spec:** `docs/superpowers/specs/2026-08-19-cota-parlamentar-design.md`

## Global Constraints

- Modelos SQLAlchemy duplicados em `api/db/models/` e `mamute_scrappers/db/models/` + os dois `__init__.py`.
- Dinheiro: `Numeric(18,2)` no banco, `Decimal` no Python, **string** no JSON (`field_serializer`).
- Migration head atual: `b8f4d2a91c57`. Revision nova na sequência hex legível, docstring com CS-57. **Sem seed de flag** (convenção: flag nasce off/oculta).
- Upsert: busca pela chave natural, `flush()` após criar, `COMMIT_EVERY=500`, lista explícita de campos sobrescritos.
- UI: `'—'` para ausente (nunca zero), `Intl.NumberFormat('pt-BR')`, link externo só via `getSafeExternalUrl`/`openSafeExternalUrl`.
- Flag: registro só em `ui/src/lib/featureFlags.ts`; gate backend via `feature_access("cota_parlamentar")`; `PREVIEW_ROWS=3` com filtros ignorados na prévia.
- Cobertura: 2022 → ano corrente.

---

### Task 1: Modelo `ParliamentaryExpense` + migration

**Files:**
- Create: `api/db/models/parliamentary_expense.py`
- Create: `mamute_scrappers/db/models/parliamentary_expense.py` (cópia idêntica)
- Modify: `api/db/models/__init__.py`, `mamute_scrappers/db/models/__init__.py` (import + `__all__`)
- Create: `mamute_scrappers/migrations/versions/c9d0e1f2a3b4_add_parliamentary_expense.py`

**Interfaces:**
- Produces: classe `ParliamentaryExpense` com colunas `id, house, source_key, parliamentarian_id, year, month, expense_type, supplier_name, supplier_id, document_number, document_date, details, document_value, glosa_value, net_value, document_url, created_at, updated_at`.

- [ ] **Step 1: modelo** (mesma estrutura do `parliamentary_amendment.py`; docstring explicando CEAP/CEAPS, SET NULL e a chave natural; `Date` para `document_date`; `UniqueConstraint("house", "source_key", name="uq_parliamentary_expense_house_source")` em `__table_args__` + `Index("ix_parliamentary_expense_parl_year", "parliamentarian_id", "year")`).
- [ ] **Step 2: migration** com `create_table` + os dois índices, `down_revision="b8f4d2a91c57"`, downgrade derruba tudo.
- [ ] **Step 3:** `alembic upgrade head` no Postgres local (docker compose dev) para validar a migration.
- [ ] **Step 4: Commit** `feat(cs57): tabela parliamentary_expense`

### Task 2: Upsert compartilhado + crawler da Câmara

**Files:**
- Create: `mamute_scrappers/expenses/__init__.py`, `mamute_scrappers/expenses/upsert.py`
- Create: `mamute_scrappers/camara_crawler/expenses.py`
- Test: `mamute_scrappers/tests/test_expenses_upsert.py`, `mamute_scrappers/tests/test_camara_expenses_parsing.py`
- Fixture: `mamute_scrappers/tests/fixtures/cota_camara_2025_sample.csv` (~10 linhas reais: 1 liderança sem ideCadastro, 1 sem ideDocumento, 1 com glosa)

**Interfaces:**
- Produces: `upsert_expense(session, payload) -> (record, created)`; `fallback_source_key(house, *parts) -> str` (sha1); `camara_crawler.expenses.build_payload(row: dict) -> Optional[dict]`; entrypoint `python -m mamute_scrappers.camara_crawler.expenses --ano YYYY [--dry-run] [--limit N] [--csv-path P]`.

- [ ] **Step 1:** testes de parse (payload de linha real; linha de liderança → parliamentarian match ausente mas payload válido; sem ideDocumento → source_key = hash estável; valores Decimal; data ISO) — rodar, FAIL.
- [ ] **Step 2:** implementar `build_payload` + download/stream do zip (requests stream → tempfile → zipfile → TextIOWrapper utf-8-sig, csv.DictReader delimiter=';') + laço com upsert e mapa `{ideCadastro: parliamentarian_id}` carregado uma vez (`type='Deputado'`). `--csv-path` para testes/reprocesso local.
- [ ] **Step 3:** testes de upsert idempotente em SQLite (cria → atualiza net_value → não duplica; unique (house, source_key)) — PASS.
- [ ] **Step 4: Commit** `feat(cs57): crawler CEAP da Câmara via arquivo anual`

### Task 3: Crawler do Senado

**Files:**
- Create: `mamute_scrappers/senado_crawler/expenses.py`
- Test: `mamute_scrappers/tests/test_senado_expenses_parsing.py`
- Fixture: `mamute_scrappers/tests/fixtures/ceaps_2025_sample.json` (~6 itens reais cobrindo os 7 tipos principais)

**Interfaces:**
- Consumes: `upsert_expense`, `fallback_source_key`.
- Produces: `build_payload(item: dict) -> Optional[dict]`; `portal_category_for(tipo_despesa: str) -> Optional[int]`; `detail_url(cod_senador, tipo_despesa, ano, mes) -> Optional[str]`; entrypoint `python -m mamute_scrappers.senado_crawler.expenses --ano YYYY [--dry-run] [--limit N]`.

- [ ] **Step 1:** testes: mapeamento dos 7 tipos → categorias {aluguel:1, material:2, locomoção:3, consultorias:4, divulgação:5, passagens:8, segurança:9} (prefixo normalizado, acento-insensível); tipo desconhecido → url None; `valorReembolsado` float → Decimal via str; source_key = str(id) — FAIL.
- [ ] **Step 2:** implementar (GET JSON com timeout/retry simples, join por `type='Senador'`).
- [ ] **Step 3:** testes PASS.
- [ ] **Step 4: Commit** `feat(cs57): crawler CEAPS do Senado via API JSON`

### Task 4: Backfill + cron

**Files:**
- Create: `mamute_scrappers/scripts/backfill_cota.py`
- Modify: `mamute_scrappers/docker/scrappers.cron` (3 blocos: diário Câmara+Senado ano corrente; backfill horário; burst @reboot)
- Test: `mamute_scrappers/tests/test_backfill_cota.py`
- Modify: `mamute_scrappers/README.md` (seção de uso, como a de emendas)

**Interfaces:**
- Consumes: entrypoints dos dois crawlers.
- Produces: chunks `cota-camara-2022 … cota-senado-{ano}`; estado em `/app/state/backfill_cota.json` (`BACKFILL_COTA_STATE_FILE`); mensagens "Backfill de cota completo|nada a fazer" (contrato do burst).

- [ ] **Step 1:** teste de `build_chunks(2022, 2026)` → 10 chunks ano×casa intercalados por ano — FAIL.
- [ ] **Step 2:** implementar (mesma mecânica do `backfill_emendas.py`: flock, subprocesso por chunk, `--status`; timeout 3600s — chunk mais pesado é CSV de 70MB local, sem rate limit).
- [ ] **Step 3:** teste PASS. Cron: diário `15 7 * * *` (Câmara) e `30 7 * * *` (Senado) — fora dos horários ocupados; backfill horário no minuto 20; burst @reboot com sleep 60.
- [ ] **Step 4: Commit** `feat(cs57): backfill e agendamento da cota parlamentar`

### Task 5: API `/expenses` + gate

**Files:**
- Create: `api/routers/expenses.py`
- Modify: `api/feature_gate.py` (`cota_access = feature_access("cota_parlamentar")` + `__all__`)
- Modify: `api/main.py` (import + `include_router(expenses.router, dependencies=auth_dependencies)`)
- Test: `api/tests/test_expenses.py`

**Interfaces:**
- Consumes: `ParliamentaryExpense`, `feature_access`, `PREVIEW_ROWS`.
- Produces:
  - `GET /api/expenses/summary?parliamentarian_id&year` → `ExpenseSummaryOut {year, total (str), count, monthly: [{month:int, expense_type:str, total:str}], top_suppliers: [{supplier_name, supplier_id, total:str, count:int}]}` — 403 sem acesso pleno.
  - `GET /api/expenses/?parliamentarian_id&year&month&limit&offset&sort_by(year|month|net_value|id)&sort_order` → `List[ExpenseOut]` (todas as colunas; dinheiro string) — prévia de 3 com filtros pinados.

- [ ] **Step 1:** testes no padrão `test_amendments.py` (SQLite DDL cru, overrides de `get_db`/`verify_token`/`cota_access`): summary agrega mês×tipo e top fornecedores ordenado; summary 403 com `full=False`; lista pagina estável e prévia corta em 3 ignorando `limit=200` — FAIL.
- [ ] **Step 2:** implementar router (summary = 2 queries GROUP BY + total; `/summary` antes de `/`).
- [ ] **Step 3:** `pytest api/tests/test_expenses.py` PASS; suíte `api/tests` inteira PASS.
- [ ] **Step 4: Commit** `feat(cs57): rotas /expenses com gate cota_parlamentar`

### Task 6: UI — flag, client e aba GASTOS

**Files:**
- Modify: `ui/src/lib/featureFlags.ts` (`cota_parlamentar`, since 2026-08-19)
- Modify: `ui/src/api/types.ts` (`ExpenseOut`, `ExpenseSummaryOut`), `ui/src/api/endpoints.ts` (`listExpenses`, `getExpensesSummary`)
- Create: `ui/src/components/dashboard/GastosTab.tsx`
- Modify: `ui/src/pages/ParlamentarDashboard.tsx` (spread condicional da aba GASTOS com `useFeatureAccess('cota_parlamentar')` + `PaywallOverlay`)
- Test: `ui/src/components/dashboard/GastosTab.test.tsx`

**Interfaces:**
- Consumes: rotas da Task 5 (paths idênticos, validados pelo contract check).
- Produces: `GastosTab({ parliamentarianId })` auto-contida (ano interno, default corrente).

- [ ] **Step 1:** tipos + client (URLSearchParams, mesmo shape do `listAmendments`).
- [ ] **Step 2:** `GastosTab`: `useQuery` summary + lista; seletor de ano (2022..corrente, shadcn Select); gráfico `BarChart` empilhado (top 6 tipos por total + "Outras"), wrapper `chart.tsx`; top fornecedores; tabela com link do documento (`getSafeExternalUrl`); estados loading/erro/vazio.
- [ ] **Step 3:** aba no dashboard (espelho exato do bloco EMENDAS).
- [ ] **Step 4:** vitest do componente (estados + pivot mensal + link) PASS; `npx tsc -p tsconfig.app.json --noEmit` sem erros novos; `python scripts/check_ui_api_contract.py` PASS.
- [ ] **Step 5: Commit** `feat(cs57): aba GASTOS com gráfico mensal, fornecedores e notas`

### Task 7: Verificação e PR

- [ ] pytest `api/tests` e `mamute_scrappers/tests` completos; vitest completo; tsc; contract check.
- [ ] Smoke real: `python -m mamute_scrappers.camara_crawler.expenses --ano 2025 --dry-run --limit 50` e o equivalente do Senado (rede real, sem persistir).
- [ ] Push + PR contra `main` com corpo-relatório (fontes, decisões, o que liga/desliga, passo pós-merge: flag off até o Luiz ligar; backfill roda sozinho no deploy).
