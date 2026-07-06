# Painéis Admin — Plano 3 (Custo/Tokens) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`).

**Goal:** Capturar tokens do OpenRouter e calcular custo por consulta, gravando em `chatbot_usage`, com uma tabela `model_pricing` (preço por modelo) sincronizável do OpenRouter. Fail-soft: falha na captura nunca quebra a resposta ao usuário.

**Architecture:** O chatbot acessa `chatbot_usage` via SQL cru; adiciono colunas `prompt_tokens`/`completion_tokens`/`cost_usd` e uma tabela `model_pricing`. `stream_usage=True` no `ChatOpenAI` + captura de `usage_metadata` no `on_llm_end`; `chat.py` repassa os tokens ao `mark_chat_usage`, que calcula o custo a partir de `model_pricing`. Como a decisão foi manter o registro **atrelado à quota** (OFF em prod), a captura só ocorre quando a quota está ligada — coerente.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic + LangChain (chatbot), pytest SQLite.

## Global Constraints
- **Fail-soft:** captura/gravação de tokens/custo nunca pode quebrar o stream nem a resposta. (spec §7)
- **Custo denormalizado:** `cost_usd` é calculado no momento do registro com o preço vigente → custo histórico estável. (spec §4.3)
- Migration na alembic compartilhada; head atual `c1d2e3f4a5b6`.
- Models duplicados: atualizar `api/db/models/chatbot_usage.py` e `mamute_scrappers/db/models/chatbot_usage.py`.

---

### Task 1: Migration + colunas + tabela `model_pricing`
- Migration `d4e5f6a7b8c9` (down_revision `c1d2e3f4a5b6`): `ALTER chatbot_usage ADD prompt_tokens INT, completion_tokens INT, cost_usd NUMERIC`; `CREATE TABLE model_pricing (id, model UNIQUE, input_usd_per_1m NUMERIC, output_usd_per_1m NUMERIC, currency TEXT default 'USD', source TEXT, updated_at)`; seed `gemini-2.5-flash` (aprox., source='seed').
- Adicionar as 3 colunas nos dois ORMs de `chatbot_usage`; criar ORM `model_pricing` em `api/db/models/`.
- Verificação: `alembic upgrade head` na base de preview.

### Task 2: Sync `model_pricing` do OpenRouter
- `scripts/sync_model_pricing.py`: `parse_openrouter_models(payload) -> list[dict]` (converte `pricing.prompt`/`.completion` USD/token → USD/1M) + upsert. `main()` faz GET `https://openrouter.ai/api/v1/models`.
- Teste do parser (payload fake).

### Task 3: Custo + tokens no `mark_chat_usage` (chatbot)
- `compute_cost_usd(prompt_tokens, completion_tokens, input_per_1m, output_per_1m) -> float|None` (pura, testável).
- `mark_chat_usage(..., prompt_tokens=None, completion_tokens=None)`: UPDATE grava tokens; SELECT em `model_pricing` pelo `model` da linha; calcula e grava `cost_usd`. TDD SQLite.

### Task 4: Captura no stream (chat_service + chat.py)
- `ChatOpenAI(..., stream_usage=True)`.
- `extract_usage(llm_result) -> dict|None` (pura) + `on_llm_end` no `JSONTokenStreamingHandler` guarda `self.usage`; `stream_response` emite `{"type":"usage",...}` antes do `end`.
- `chat.py`: captura o evento usage e repassa tokens a `_mark_usage`→`mark_chat_usage`. Tudo fail-soft.
- Teste unitário de `extract_usage` (objeto duck-typed).

### Task 5: Validação local
- Semear `model_pricing` + rodar consultas (ou seed manual de `chatbot_usage` com tokens) e conferir `cost_usd`.

## Self-Review
Cobre spec §4.3 e §5 Plano 3 (tokens, custo, model_pricing, OpenRouter, fail-soft). Captura só com quota ligada (decisão do Luiz: registro atrelado à quota).
