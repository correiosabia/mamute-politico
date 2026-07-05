# Painéis Admin — Plano 5 (Drill-down + Instrumentação de uso) Plan

> REQUIRED SUB-SKILL: superpowers:executing-plans.

**Goal:** Instrumentar uso do sistema (navegação + trocas de parlamentares) e um drill-down por usuário no painel de métricas, mostrando comportamento individual (IA no tempo, páginas mais usadas, frequência de troca, favoritos, plano vs consumo).

**Architecture:** Eventos de favorito são logados **server-side** nas rotas existentes (fonte da verdade). `page_view` vem de um **beacon no front** para `POST /api/events` (auth de membro). Tudo grava em `usage_events`. O drill-down `GET /admin/metrics/users/{id}` (admin) agrega esses dados + `chatbot_usage`.

**Decisões (Luiz):** sem captura de conteúdo/tópico de IA na v1; instrumentar navegação/trocas; drill-down de usuário antes do painel de cobertura; tudo numa branch (sem PR ainda).

## Global Constraints
- Ingesta de eventos nunca pode quebrar o app (fail-soft); logging de favorito não pode quebrar a ação de favoritar.
- Migration na alembic compartilhada; head atual `d4e5f6a7b8c9`.
- Sem armazenar texto de perguntas de IA.

## Tasks
1. **usage_events**: model (`api/db/models/usage_event.py`) + migration `e5f6a7b8c9d0` (id, projeto_id, email, event_type, page, parliamentarian_id, created_at) + índices (projeto_id, event_type, created_at).
2. **Ingest** `POST /api/events` (`api/routers/events.py`, auth de membro): body `{events:[{type:'page_view', page:str}]}`; resolve projeto por email; insere. Registrar no main. Teste.
3. **Log server-side de favoritos**: em `projects.py` `_create_project_favorite`/`_delete_project_favorite`, gravar `favorite_added`/`favorite_removed` (fail-soft). Teste.
4. **Drill-down** `metrics_user_detail(db, projeto_id, period_start, rate)` + rota `GET /admin/metrics/users/{id}`: retorna dados do usuário + IA por dia + páginas mais usadas + contagem de trocas + favoritos atuais + plano/limites/consumo. Teste.
5. **Front**: beacon de `page_view` (hook no router, ignora /admin) + página `AdminUserDetailPage` (`/admin/metrics/users/:id`), linkada ao clicar na linha da tabela de métricas.
6. **Preview**: semear usage_events + screenshot.

## Self-Review
Cobre a decisão de instrumentar navegação/trocas e o drill-down; sem conteúdo de IA. Cobertura do banco (Senado/Câmara) fica para o Plano 6.
