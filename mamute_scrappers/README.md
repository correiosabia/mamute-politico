# Mamute Scrappers

Módulo responsável pela coleta e sincronização de dados legislativos (Câmara e Senado), além de rotinas auxiliares de atualização.

Projeto pai: [README raiz](../README.md)

## Pré-requisitos

- Python 3.11+
- PostgreSQL acessível via `DATABASE_URL`

## Inicialização

1. Entre na pasta dos scrappers:

   ```bash
   cd mamute_scrappers
   ```

2. Crie e ative o ambiente virtual:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. Instale dependências:

   ```bash
   pip install -r requirements.txt
   ```

4. Configure variáveis de ambiente:

   ```bash
   cp .env.example .env
   ```

   Ajuste no mínimo `DATABASE_URL`. Para análise com OpenAI, configure também
   `OPENAI_API_KEY`. Para backfill manual de usuários do Ghost, configure
   `GHOST_API_KEY` e `GHOST_ADMIN_URL`.

5. Rode as migrações:

   ```bash
   alembic upgrade head
   ```

## Execução dos programas principais

### Coleta de pronunciamentos do Senado

```bash
python -m mamute_scrappers.senado_crawler.speechs_transcipts --help
```

### Coleta de discursos/transcrições da Câmara

Execute a partir da raiz do projeto (`mamute-politico`):

```bash
python -m mamute_scrappers.camara_crawler.speeches_transcripts --help
```

Exemplos:

```bash
# todos os deputados (persistindo no banco)
python -m mamute_scrappers.camara_crawler.speeches_transcripts

# deputado específico a partir de uma data
python -m mamute_scrappers.camara_crawler.speeches_transcripts --deputado-id 1234 --data-inicio 2026-01-01

# teste sem persistir no banco
python -m mamute_scrappers.camara_crawler.speeches_transcripts --dry-run
```

### Reprocessar análise de texto de pronunciamentos

```bash
python -m mamute_scrappers.scripts.rebuild_speech_text_analysis --help
```

### Reconciliar usuários/projetos via Ghost

```bash
python -m mamute_scrappers.scripts.create_users
```

Esse comando é um backfill manual. A sincronização contínua Ghost -> projetos é
recebida pela API em `POST /api/webhooks/ghost/members`.

## Cronjobs recomendados

Exemplo de configuração para atualização contínua de projetos, trâmites e dados auxiliares:

```cron
##########################
# MAMUTE POLITICO
##########################
PROJECT_ROOT=mamute-politico
PYTHON_BIN=mamute-politico/.venv/bin/python
LOG_DIR=mamute-politico/mamute_scrappers/.logs

# Sync Ghost -> projetos é feito via webhook da API.
# Rode mamute_scrappers.scripts.create_users manualmente apenas para reconciliação.

# Novas proposições/projetos (a cada 6h)
0 */6 * * *   cd $PROJECT_ROOT && $PYTHON_BIN -m mamute_scrappers.senado_crawler.proposition >> $LOG_DIR/crawlers/propositions.log 2>&1

# Atualização de trâmites/status (diário às 03h)
0 3 * * *     cd $PROJECT_ROOT && $PYTHON_BIN -m mamute_scrappers.senado_crawler.proposition_status >> $LOG_DIR/crawlers/proposition_status.log 2>&1

# Tipos de proposição (diário às 04h)
0 4 * * *     cd $PROJECT_ROOT && $PYTHON_BIN -m mamute_scrappers.senado_crawler.proposition_type >> $LOG_DIR/crawlers/proposition_type.log 2>&1

# Votações nominais (a cada 3h)
0 */3 * * *   cd $PROJECT_ROOT && $PYTHON_BIN -m mamute_scrappers.senado_crawler.roll_call_votes >> $LOG_DIR/crawlers/roll_call_votes.log 2>&1

# Discursos/taquigrafias (a cada 2h)
0 */2 * * *   cd $PROJECT_ROOT && $PYTHON_BIN -m mamute_scrappers.senado_crawler.speechs_transcipts >> $LOG_DIR/crawlers/speechs_transcripts.log 2>&1

# Parlamentares da Câmara (diário às 05h30)
30 5 * * *    cd $PROJECT_ROOT && $PYTHON_BIN -m mamute_scrappers.camara_crawler.parliamentarian >> $LOG_DIR/crawlers/camara_parliamentarians.log 2>&1
```

## Observações

- Use `--help` nos comandos para ver todos os parâmetros disponíveis.
- É recomendado executar os scrappers antes de iniciar `api` e `chatbot_backend`.
