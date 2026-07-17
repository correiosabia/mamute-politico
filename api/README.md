# API Mamute

Aplicação FastAPI para expor os dados coletados no projeto.

Projeto pai: [README raiz](../README.md)

## Pré-requisitos

- Python 3.11+
- Banco PostgreSQL já populado pelos scrappers

## Inicialização

1. Entre na pasta da API:

   ```bash
   cd api
   ```

2. Crie e ative o ambiente virtual:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. Instale as dependências:

   ```bash
   pip install -r requirements.txt
   ```

4. Configure variáveis de ambiente:

   ```bash
   cp .env.example .env
   ```

   Ajuste principalmente `DATABASE_URL`, as variáveis do Ghost Members e
   `GHOST_WEBHOOK_SECRET` se for receber webhooks do Ghost.

5. Inicie a API:

   ```bash
   uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
   ```

## Endereços locais

- API (rotas): prefixo `http://127.0.0.1:8000/api` (ex.: `/api/parliamentarians`, `/api/analysis/...`)
- Docs Swagger: `http://127.0.0.1:8000/api/docs`

## Observações

- Rotas protegidas exigem `Authorization: Bearer <token>` com JWT emitido pelo Ghost Members.
- O endpoint `POST /api/webhooks/ghost/members` recebe eventos `member.added`,
  `member.edited` e `member.deleted` do Ghost. Configure o mesmo segredo no
  Ghost Admin e em `GHOST_WEBHOOK_SECRET`. Passo a passo:
  [`../environments/ghost.md`](../environments/ghost.md).
- Quando `GHOST_API_KEY`/`GHOST_ADMIN_URL` estão disponíveis, o webhook consulta
  o member completo no Ghost Admin API antes de sincronizar o projeto local. Isso
  evita cair em `free` quando o payload do evento não traz `tiers/subscriptions`.
- A API também roda reconciliação Ghost -> tiers/projetos no startup por padrão.
  Desative com `MAMUTE_GHOST_RECONCILE_ON_STARTUP=false` se necessário.
- Em caso de rotação de chaves JWKS, reinicie a aplicação para recarregar a chave pública.
- O deployment define `MAMUTE_PARLIAMENTARIAN_CATALOG_SCOPE` para controlar a
  visibilidade do catálogo: `current_only` (padrão seguro),
  `current_and_licensed` ou `all_ingested`. A API aplica essa política a toda
  consulta e a expõe, para clientes autenticados, em
  `GET /api/parliamentarians/catalog-config`.
