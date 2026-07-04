# Spec — Painéis Admin (Ghost) do Mamute: Gestão de Tiers + Métricas/Insights

**Data:** 2026-07-04 · **Status:** aprovado para planejamento
**Antecedentes:** `.claude/handoffs/2026-07-03-paineis-admin-ghost-tiers-metricas.md`, memória `project_paineis_admin_ghost`.

## 1. Objetivo

Dois painéis dentro do app do Mamute, acessíveis **somente por administradores**, atrás de feature flag:

1. **Gestão** — editar a config de tiers (limites por plano) no banco, sem redeploy.
2. **Métricas/Insights** — KPIs de uso por usuário: chamadas de IA, tokens/custo, mensagens/sessões, parlamentares monitorados, plano vs consumo, margem (preço − custo), features mais usadas.

Enforcement do acesso é **100% server-side**. Esconder a aba no front é só UX.

## 2. Decisões fechadas

| Tema | Decisão |
|---|---|
| Identificação de admin | **Allowlist de e-mails** (env), checada contra o `sub` do JWT Ghost. Lógica isolada numa função (`require_ghost_admin`) para trocar por Ghost Admin API no futuro sem mexer nas rotas. |
| Escopo v1 | **Completo**: gate + gestão de tiers + captura de custo/tokens + métricas/margem. |
| Origem do preço do plano | **Config do tier** — `preco_mensal` em `tiers.detalhes`, editável no painel de gestão. |
| Home do backend | **`api/`** para todas as rotas `/admin/*`. Exceção: captura de tokens fica no `chatbot_backend/`. |
| Resposta para não-admin | **404** no router `/admin` inteiro (esconde a existência), não 403. |
| Feature flag | Env `MAMUTE_ADMIN_PANELS_ENABLED` (default `false`). |
| Preços de modelo | Tabela `model_pricing`, semeada/atualizável a partir do endpoint `GET /api/v1/models` do OpenRouter; linha por modelo, com override manual editável. |
| Entrega | **Um spec, quatro planos sequenciais** (cada um shippável). Cada plano é **validado/testado localmente antes de abrir PR** (ver §8). |

## 3. Fundações confirmadas no código

- **JWT Ghost**: validado via JWKS (RS512) com audience/issuer; claim `sub` = e-mail do membro. **Não há role/staff** hoje — "admin" é camada 100% nova. (`api/security.py:88-122`, `chatbot_backend/app/security.py:97-131`)
- **Tiers no DB**: `tiers.detalhes` (JSONB) + `product_id` (SKU Ghost, unique) + FK `projetos.tier_id → tiers.id`. (`mamute_scrappers/db/models/project.py:24-192`)
- **Precedência atual**: env `>` DB em `quota.py:resolve_monthly_limit` (161-188). Precisa **inverter**.
- **`chatbot_usage`**: só `question_chars`/`answer_chars`/`model`; **sem tokens/custo**. `usage` do OpenRouter é descartado. (`chatbot_backend/app/services/chat_service.py:197-227`, `services/quota.py:309-345`)
- **Sem Stripe** no repo; preço só vive no Ghost (fora do código).
- **Front**: React 18 + React Router 6 + TanStack Query + shadcn/ui; JWT no `localStorage` (`ghost_jwt_token`) enviado como `Bearer`; `RequireAuth` já existe. (`ui/src/App.tsx`, `ui/src/api/client.ts`)
- **Settings**: `pydantic BaseSettings` + `@lru_cache` (lido no startup). A config de tier vem do DB por request, então edições valem sem redeploy.

## 4. Arquitetura

### 4.1 Backend
- Novo router `api/routers/admin.py` (ou pacote `api/routers/admin/`) com **todas** as rotas `/admin/*`.
- Dependency **`require_ghost_admin`** (`api/security.py` ou módulo novo):
  1. reusa `verify_token` (valida JWT Ghost);
  2. normaliza `sub` → e-mail lowercase;
  3. checa `MAMUTE_ADMIN_PANELS_ENABLED` **e** e-mail ∈ `MAMUTE_ADMIN_EMAILS`;
  4. falha → **404** (não vaza existência da superfície).
  - Toda a lógica "é admin?" fica **nesta função** — ponto único de troca para Ghost Admin API.
- `chatbot_backend/` recebe apenas a mudança de captura de tokens no fluxo de chat.

### 4.2 Frontend
- `ui/src/routes/admin/` com `RequireAdmin` (chama `GET /admin/whoami`; se 404/erro, não é admin), `AdminLayout`, `TiersPanel`, `MetricsPanel`.
- Hooks em `ui/src/api/admin.ts` (TanStack Query). Aba escondida quando não-admin (UX; segurança é o 404).
- Gráficos com `recharts`.

### 4.3 Dados novos
- Colunas em `chatbot_usage`: `prompt_tokens` (int), `completion_tokens` (int), `cost_usd` (numeric).
- Tabela `model_pricing`: `model` (text, unique), `input_usd_per_1m` (numeric), `output_usd_per_1m` (numeric), `currency` (text, default `USD`), `source` (text: `openrouter`|`manual`), `updated_at`.
- Tabela `admin_audit_log`: `id`, `admin_email`, `action`, `entity`, `entity_id`, `before` (JSONB), `after` (JSONB), `created_at`.
- Campo `preco_mensal` (numeric) dentro de `tiers.detalhes`.

## 5. Faseamento (4 planos)

### Plano 1 — Gate (Fase 0)
- Env `MAMUTE_ADMIN_EMAILS`, `MAMUTE_ADMIN_PANELS_ENABLED`.
- `require_ghost_admin` + router `/admin` com 404 para não-admin/flag off.
- `GET /admin/whoami` (valida o gate ponta-a-ponta).
- Tabela `admin_audit_log` (schema + migration).
- Front: `RequireAdmin` + shell `/admin` + aba condicional.
- **Critério de aceite:** admin abre `/admin` e vê "hello admin"; não-admin recebe 404 na API e não vê a aba; teste server-side confirma que não-admin não lê nada.

### Plano 2 — Painel de Gestão (Fase 1)
- `GET /admin/tiers`, `PUT /admin/tiers/{id}` com validação Pydantic (`qtd_termos`, `qtd_consultas_ia_mes`, `qtd_email`, `periodicidade_email`, `orgao`, `preco_mensal`).
- **Inverter precedência**: DB (`tier.detalhes`) ganha em `quota.py:resolve_monthly_limit` e no resolver de tier de `api/routers/projects.py`; env vira bootstrap/fallback.
- **Bootstrap**: migrar valores de `MAMUTE_TIER_LIMITS_JSON` para `tiers.detalhes` (script/migration idempotente).
- Todo write loga em `admin_audit_log` (before/after).
- Front: `TiersPanel` (form por tier, validação, feedback).
- **Critério de aceite:** editar `qtd_consultas_ia_mes` no painel altera o limite efetivo **sem redeploy**; auditoria registra a mudança; quota (quando ligada) lê do DB.

### Plano 3 — Captura de custo/tokens (Fase C)
- `ChatOpenAI(..., stream_usage=True)`; capturar `usage_metadata` do chunk final (sem chamada extra).
- Gravar `prompt_tokens`/`completion_tokens` no `_mark_usage(...completed...)` e calcular `cost_usd` com o preço vigente de `model_pricing` (**denormalizado** → custo histórico estável).
- Tabela `model_pricing` + migration; seed/refresh a partir de `GET https://openrouter.ai/api/v1/models` (`pricing.prompt`/`pricing.completion` são USD/token → converter para USD/1M). Endpoint admin `POST /admin/model-pricing/sync` (opcional) + edição manual.
- **Critério de aceite:** após uma conversa real, a linha em `chatbot_usage` tem tokens e `cost_usd` coerente com o preço do gemini; alterar preço no futuro não muda custo histórico.

### Plano 4 — Painel de Métricas (Fase D)
- `GET /admin/metrics/overview` (usuários ativos, chamadas IA/mês, custo total, receita total, margem).
- `GET /admin/metrics/users` (por usuário: plano, chamadas mês/total, tokens, `cost_usd`, msgs/sessões, nº parlamentares monitorados, `preco_mensal`, margem, flag consumo-vs-plano).
- `GET /admin/metrics/features` (uso derivável hoje: chat, favoritos, notas).
- Front: `MetricsPanel` (KPI cards + tabela por usuário + gráficos recharts).
- **Critério de aceite:** dashboard mostra margem por usuário (preço − custo) e sinaliza quem consome acima do plano; todos os endpoints admin-gated.

## 6. Fora de escopo (v1)
- Ghost Admin API (admin automático via staff/roles) — evolução da allowlist.
- Instrumentação fina de eventos para "features mais usadas" além do derivável.
- Integração com Stripe/faturamento real (preço fica no config do tier).
- Allowlist de admin em tabela DB editável (v1 usa env).

## 7. Validação local antes de PR

Cada plano só vira PR **depois de rodar e validar localmente** (stack em Docker Compose; só Postgres nativo — ver memória `project_docker_migration`). Roteiro por plano:

- **Plano 1 (Gate):** subir `api/` + `ui/` local; logar com e-mail na allowlist → `/admin/whoami` OK e aba visível; logar com e-mail fora da allowlist → **404** na API e aba ausente; com flag off → 404 mesmo para admin.
- **Plano 2 (Gestão):** editar `qtd_consultas_ia_mes` de um tier pelo painel; confirmar no DB que `tiers.detalhes` mudou e que o limite efetivo (via resolver) reflete **sem reiniciar**; conferir linha em `admin_audit_log`; rodar o bootstrap env→DB e validar idempotência.
- **Plano 3 (Custo/tokens):** rodar uma conversa real no chatbot local; conferir `chatbot_usage` com `prompt_tokens`/`completion_tokens`/`cost_usd` coerentes; simular falha na captura e confirmar **fail-soft** (resposta ao usuário intacta); rodar o sync do OpenRouter e checar `model_pricing`.
- **Plano 4 (Métricas):** abrir o dashboard local; conferir overview/por-usuário/features contra números esperados do DB; confirmar que todos os endpoints são 404 para não-admin.

Além dos testes automatizados de cada plano, essa passada manual é pré-requisito do PR.

## 8. Riscos & mitigação
- **Escrita em config de produção** (Plano 2): validação de schema + auditoria (`admin_audit_log`).
- **Inverter precedência** muda comportamento de quota: risco baixo hoje (quota **desligada** em prod); mudar a lógica e bootstrap **antes** de ligar `MAMUTE_CHATBOT_QUOTA_ENABLED`.
- **Mexer no fluxo de chat em prod** (Plano 3): `stream_usage` isolado, testável; falha na captura de tokens **não pode** quebrar a resposta ao usuário (fail-soft: loga sem tokens).
- **Gate**: enforcement server-side com teste explícito de que não-admin recebe 404 e não lê dado nenhum; nunca confiar no front.
