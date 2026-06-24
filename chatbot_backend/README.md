# Mamute Político Chatbot Backend

Backend construído com FastAPI e LangChain para oferecer um chatbot especializado nas notas taquigráficas, combinando busca vetorial no PostgreSQL (pgvector) e consultas SQL auxiliares.

Projeto pai: [README raiz](../README.md)

## Estrutura

- `app/` – código da aplicação FastAPI (rotas, serviços e configurações)
- `scripts/` – utilitários para ingestão de dados no índice vetorial
- `.env.example` – modelo de variáveis de ambiente
- `requirements.txt` – dependências isoladas do backend

## Pré-requisitos

1. Python 3.11+
2. Banco PostgreSQL com extensão [`pgvector`](https://github.com/pgvector/pgvector) habilitada
3. Chave de API do OpenAI (modelo GPT e embeddings)

## Inicialização

1. Crie e ajuste o arquivo de variáveis de ambiente:

   ```bash
   cp chatbot_backend/.env.example chatbot_backend/.env
   ```

   Edite o `.env` com suas credenciais de banco e chaves do OpenAI. Os campos `APPLICATION_NAME` (PostgreSQL) e `RERANK_TOP_K` (reranqueador) permitem ajustes de monitoramento e qualidade das respostas.

2. Crie um ambiente virtual e instale as dependências:

   ```bash
   cd chatbot_backend
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Inicialize a coleção vetorial

Com as variáveis `DATABASE_URL` e `PGVECTOR_CONNECTION` apontando para o banco desejado:

```bash
python -m chatbot_backend.scripts.init_vector_collection
```

O script garante que as extensões necessárias (`vector`, `pgcrypto`) estejam ativas, cria as tabelas padrão (`langchain_pg_collection`, `langchain_pg_embedding`), configura índices e registra a coleção definida em `PGVECTOR_COLLECTION`. Caso já exista, nada é sobrescrito. Use `--dimension 3072` para informar manualmente a dimensão do vetor (por padrão é detectada via API do OpenAI).

> Observação: se preferir não expor `OPENAI_API_KEY` nesse momento, utilize o parâmetro `--dimension` para evitar a chamada à API de embeddings.
>
> Limite de índices: o índice IVFFLAT não é criado automaticamente quando a dimensão do embedding excede 2000 (limitação do pgvector). Para embeddings maiores, considere usar um modelo menor (`text-embedding-3-small`, 1536 dimensões) ou criar manualmente uma estratégia alternativa (por exemplo, HNSW quando disponível).

Caso o banco já tenha um esquema anterior (ex.: tabelas criadas com outra estrutura), rode com `--reset` para remover e recriar:

```bash
python -m chatbot_backend.scripts.init_vector_collection --reset --dimension 3072
```

## Indexação das notas taquigráficas

Use o script de ingestão para popular o índice vetorial no pgvector:

```bash
python -m chatbot_backend.scripts.ingest_transcripts --batch-size 200
```

O script lê as notas diretamente da tabela `speeches_transcripts`, cria chunks com `RecursiveCharacterTextSplitter` e adiciona documentos ao índice definido em `PGVECTOR_COLLECTION`.

Cada chunk recebe metadados `speech_id`, `parliamentarian_id`, `date`, `session_number` e `type`, permitindo rastreamento e filtros posteriores no JSONB (`cmetadata`) armazenado no PostgreSQL.
## Sincronização contínua

Para manter o índice atualizado, execute periodicamente:

```bash
python -m chatbot_backend.scripts.sync_transcripts --window-hours 6
```

O comando carrega discursos inseridos/atualizados na janela especificada, remove chunks anteriores do mesmo discurso e reindexa os novos. Utilize `--since 2024-03-01T00:00:00Z` para sincronizar a partir de um instante fixo ou `--dry-run` para apenas inspecionar o que seria carregado.

## Executando a API

Inicie o servidor FastAPI em modo desenvolvimento com:

```bash
uvicorn chatbot_backend.app.main:app --reload --host 0.0.0.0 --port 8001
```

Endpoints principais:

- `POST /chat/chatbot/stream` – responde em streaming via Server-Sent Events (`text/event-stream`).
- `POST /chat/chatbot/query` – retorna a resposta completa sem streaming.
- `GET /chat/chatbot/quota` – retorna uso e limite mensal de consultas IA quando a quota está ativa.
- `GET /chat/health` – verificação simples de saúde.

## Quota mensal por tier

As rotas `stream` e `query` sempre exigem `Authorization: Bearer <Ghost Members JWT>`.
`MAMUTE_CHATBOT_QUOTA_ENABLED` controla apenas a contabilização mensal de uso. Por padrão,
a quota fica desligada para manter compatibilidade com deployments existentes, mas isso não
abre os endpoints de IA para chamadas anônimas:

```bash
MAMUTE_CHATBOT_QUOTA_ENABLED=false
MAMUTE_CHATBOT_DEFAULT_MONTHLY_LIMIT=0
MAMUTE_TIER_LIMITS_JSON={"free":{"qtd_termos":1,"qtd_consultas_ia_mes":0},"default-product":{"qtd_termos":3,"qtd_consultas_ia_mes":50},"cidadao-mamute":{"qtd_termos":10,"qtd_consultas_ia_mes":200}}
MAMUTE_CHATBOT_MONTHLY_LIMITS_JSON=
MAMUTE_CHATBOT_QUOTA_FAIL_OPEN=false
```

Quando `MAMUTE_CHATBOT_QUOTA_ENABLED=true`, o serviço resolve o projeto pelo e-mail (`sub`) do token, descobre o slug do tier em `tiers.detalhes.ghost.slug` e aplica o limite mensal.

Precedência do limite:

1. `MAMUTE_CHATBOT_MONTHLY_LIMITS_JSON` por slug do Ghost, se usado como override específico do chatbot.
2. `MAMUTE_TIER_LIMITS_JSON[slug].qtd_consultas_ia_mes`, compartilhado com outros limites do app.
3. `tiers.detalhes.qtd_consultas_ia_mes`, se existir.
4. `MAMUTE_CHATBOT_DEFAULT_MONTHLY_LIMIT`.
5. Sem configuração, o limite efetivo é `0`.

O mesmo `MAMUTE_TIER_LIMITS_JSON` também pode controlar o limite de parlamentares monitorados na API principal com `qtd_termos`, por exemplo:

```json
{
  "free": {"qtd_termos": 1, "qtd_consultas_ia_mes": 0},
  "default-product": {"qtd_termos": 3, "qtd_consultas_ia_mes": 50},
  "cidadao-mamute": {"qtd_termos": 10, "qtd_consultas_ia_mes": 200}
}
```

O uso é gravado em `chatbot_usage` sem armazenar pergunta ou resposta bruta. Uma consulta conta a partir do momento em que é iniciada, inclusive se for cancelada, falhar ou terminar normalmente.

### Formato do streaming

Cada evento é retornado no padrão SSE, por exemplo:

```text
data: {"type":"token","value":"Olá"}

data: {"type":"token","value":"!"}

data: {"type":"done"}
```

No front-end basta consumir o endpoint com `EventSource` (ou fetch streaming) para reconstruir o texto.

Exemplo de requisição com filtros (limitando a partidos específicos):

```bash
curl -N \
  -H "Content-Type: application/json" \
  -d '{
        "question": "Quais parlamentares discutiram a reforma tributária?",
        "filters": {
          "parties": ["UNIÃO", "PT"]
        }
      }' \
  http://localhost:8001/chat/chatbot/stream
```

Campos aceitos dentro de `filters`: `parliamentarian_ids` (lista de IDs numéricos), `parties` (siglas), `states` (UFs) e `roles` (tipos de parlamentares). Todos são opcionais; se nenhum filtro for enviado, a busca considera todo o conjunto disponível.
## Personalizações

- Ajuste `RETRIEVER_K` e `RETRIEVER_SCORE_THRESHOLD` para calibrar a quantidade de chunks trazidos do vetor.
- Ajuste `RERANK_TOP_K` para definir quantos chunks reranqueados alimentam o prompt final; o reranqueador usa o próprio modelo GPT para priorizar trechos mais relevantes.
- Modifique `SQL_CONTEXT_LIMIT` e a lista de stopwords em `SQL_KEYWORD_STOPWORDS` para adaptar as consultas SQL acessórias.
- Controle o volume de estatísticas agregadas retornadas com `SQL_FREQUENCY_LIMIT`; perguntas sobre “quantidade”, “frequência” ou “quantas vezes” ativam uma consulta de contagem por parlamentar.
- Ajuste `SQL_KEYWORDS_LIMIT`, `SQL_ENTITIES_LIMIT` e `SQL_PROPOSITIONS_LIMIT` para calibrar quantos resultados são trazidos das tabelas de palavras-chave, entidades nomeadas e proposições associadas.
- O prompt base está em `app/services/prompts.py`.
- A coleção vetorial possui índice dedicado em `(cmetadata->>'parliamentarian_id')::bigint`, permitindo buscas eficientes por parlamentar específico.

## Passo a passo sugerido

1. Configure o `.env` com as credenciais de banco e do OpenAI.
2. Crie e ative um ambiente virtual, instalando `pip install -r requirements.txt`.
3. Rode `python -m chatbot_backend.scripts.init_vector_collection` para preparar a coleção vetorial.
4. Execute `python -m chatbot_backend.scripts.ingest_transcripts` para popular o índice inicial.
5. Agende `python -m chatbot_backend.scripts.sync_transcripts` (cron/job) para manter o índice atualizado.
6. Suba a API com `uvicorn chatbot_backend.app.main:app --reload --port 8001`.
7. Consuma `/chat/chatbot/query` ou `/chat/chatbot/stream` a partir do front-end (no stack com Caddy em `:80`, use `http://localhost/chat/...`).

## Observabilidade

Caso utilize LangSmith/LangChain tracing, habilite `LANGCHAIN_TRACING_V2=true` e defina `LANGCHAIN_PROJECT` no `.env`.

## Testes recomendados

- Verifique o endpoint `POST /chat/chatbot/query` com uma pergunta conhecida para validar a recuperação.
- Monitore o banco para garantir que o índice vetorial está sendo populado corretamente.
- Consuma `POST /chat/chatbot/stream` via curl (`curl -N`) e observe o fluxo de tokens.
