# CS-57 — Cota parlamentar: gastos de gabinete por mês, tipo e fornecedor, com nota fiscal

Data: 2026-08-19 · Task: [CS-57](https://lvdev.atlassian.net/browse/CS-57) · Status: aprovado pelo Luiz em 19/08/2026

## Objetivo

Coletar, armazenar e exibir os gastos da cota parlamentar (CEAP da Câmara e
CEAPS do Senado) por parlamentar, com visão mensal por tipo de despesa e
fornecedor, e link para o documento fiscal quando a fonte publicar.

## Levantamento das fontes (fechado em 19/08/2026)

### Câmara — CEAP

- A API REST `GET /api/v2/deputados/{id}/despesas` está **degradada**: devolve
  `x-total-count: 0` com `retry-after: 30` para todos os deputados e anos
  testados (2024–2026). Mesmo comportamento observado no teste de 12/08 citado
  na task. **Não usar.**
- Fonte adotada: **arquivo anual em massa**
  `https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip` (~7,5 MB zipado, ~70 MB
  CSV, ~208 mil linhas/ano). Atualizado **diariamente** pela Câmara
  (last-modified de madrugada). Cobertura verificada: 2008→2026.
- Colunas relevantes: `ideCadastro` (id do deputado nos dados abertos — igual
  ao nosso `parliamentarian_code` com `type='Deputado'`), `txtDescricao` (tipo
  de despesa), `txtFornecedor`, `txtCNPJCPF`, `txtNumero`, `datEmissao`,
  `vlrDocumento`, `vlrGlosa`, `vlrLiquido`, `numMes`, `numAno`, `txtPassageiro`,
  `txtTrecho`, `ideDocumento`, `urlDocumento`.
- `urlDocumento` é **PDF público direto** (testado: 200 `application/pdf`).
- Gotchas: linhas de liderança partidária vêm com `ideCadastro` vazio; algumas
  despesas (telefonia, correios) não têm `ideDocumento`/`urlDocumento`;
  encoding UTF-8 com BOM; separador `;`.

### Senado — CEAPS

- Fonte adotada: **API JSON**
  `https://adm.senado.gov.br/adm-dadosabertos/api/v1/senadores/despesas_ceaps/{ano}`
  (~24 mil linhas/ano). Cobertura verificada: 2008→2026, atualizada diariamente.
- Campos: `id`, `ano`, `mes`, `codSenador`, `nomeSenador`, `tipoDespesa`,
  `cpfCnpj`, `fornecedor`, `documento`, `data`, `detalhamento`,
  `valorReembolsado`, `tipoDocumento`.
- `codSenador` **é** o `CodigoParlamentar` dos dados abertos do Senado — o
  mesmo valor que já guardamos em `parliamentarian_code` com `type='Senador'`
  (verificado: 475 = Confúcio Moura). **Nenhuma das casas exige casamento por
  nome** — diferença importante vs. emendas.
- O CSV alternativo (`senado.leg.br/transparencia/LAI/verba/despesa_ceaps_{ano}.csv`)
  existe mas é pior: latin-1, senador só por nome, sem id de senador. Não usar.

### Documento fiscal do Senado

- O id do PDF de download
  (`www6g.senado.leg.br/transparencia/sen/download/ceaps/documento/{n}`) **não
  existe** no CSV nem na API — é um terceiro espaço de ids que só aparece nas
  páginas HTML do portal. `COD_DOCUMENTO` do CSV e `id` da API testados: 404.
- **Decisão**: linkar a **página de detalhe do portal**, que é determinística:
  `https://www6g.senado.leg.br/transparencia/sen/{codSenador}/ceaps/{categoria}/detalhe/?mesAno=MM/AAAA`.
  O comprovante fica a um clique, na página oficial. O mapeamento
  `tipoDespesa → categoria` do portal é levantado empiricamente na
  implementação; tipo sem mapeamento → `document_url` NULL (degradação
  aceitável). Scraping dos ids de download foi descartado (frágil, caro,
  exigiria casar despesa por fornecedor/data/valor).

## Decisões de produto (Luiz, 19/08/2026)

- **Cobertura histórica: 2022 → hoje** (mesmo recorte das emendas). Backfill
  extensível no futuro. Volume estimado: ~880k linhas Câmara + ~100k Senado.
- **UI**: aba nova no perfil com gráfico mensal por tipo + top fornecedores +
  tabela detalhada.
- **Flag `cota_parlamentar` nasce `off` e oculta em todos os planos, sem
  seed** — convenção do projeto daqui em diante: quem liga e recorta por plano
  é o Luiz, pelas telas de admin.

## Arquitetura

Escolha central: **tabela única de despesas + agregação on-the-fly**. Com ~1M
de linhas e consultas sempre filtradas por parlamentar+ano (poucas centenas de
linhas por grupo, índice composto), `GROUP BY` direto resolve; tabela de rollup
mensal seria complexidade e risco de dessincronização sem ganho. Tabelas
separadas por casa também descartadas — discriminador `house`, como
`parliamentarian.type`.

### Modelo de dados

Tabela `parliamentary_expense` (modelo duplicado em `api/db/models/` e
`mamute_scrappers/db/models/`, como todas):

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | BigInteger PK | |
| `house` | Text NOT NULL | `camara` \| `senado` |
| `source_key` | Text NOT NULL | Chave natural de upsert. Câmara: `ideDocumento`; Senado: `id` da API; fallback (Câmara sem `ideDocumento`): hash determinístico da linha. **Unique `(house, source_key)`** |
| `parliamentarian_id` | FK → parliamentarian, **SET NULL**, nullable, index | Fato público não some (mesma decisão das emendas). NULL para legislatura 56 fora da base e lideranças |
| `year`, `month` | Integer NOT NULL | Índice composto `(parliamentarian_id, year)` |
| `expense_type` | Text NOT NULL | Texto cru da fonte (taxonomias diferentes por casa; sem normalização inventada) |
| `supplier_name` | Text | |
| `supplier_id` | Text | CNPJ/CPF como publicado |
| `document_number` | Text | `txtNumero` / `documento` |
| `document_date` | Date | `datEmissao` / `data` |
| `details` | Text | Câmara: passageiro+trecho; Senado: `detalhamento` |
| `document_value` | Numeric(18,2) | Câmara `vlrDocumento`; Senado NULL |
| `glosa_value` | Numeric(18,2) | Câmara `vlrGlosa`; Senado NULL |
| `net_value` | Numeric(18,2) NOT NULL | Câmara `vlrLiquido`; Senado `valorReembolsado` |
| `document_url` | Text | Câmara: PDF direto; Senado: página de detalhe do portal; NULL quando a fonte não publica |
| `created_at`, `updated_at` | timestamptz | `server_default=func.now()` / `onupdate` |

Migration em `mamute_scrappers/migrations/versions/`, revision na sequência
hex legível do projeto, docstring com justificativa e CS-57.

### Coleta

Crawlers novos, um por casa (crawler mora no pacote da fonte):

- `mamute_scrappers/camara_crawler/expenses.py` — baixa o zip anual, faz
  stream-parse do CSV, pula linhas sem `ideCadastro` (logando contagem), join
  `parliamentarian_code == ideCadastro AND type='Deputado'`.
- `mamute_scrappers/senado_crawler/expenses.py` — GET no JSON anual, join
  `parliamentarian_code == codSenador AND type='Senador'`; monta
  `document_url` da página de detalhe via mapeamento tipo→categoria.

Receituário do `emendas.py` em ambos: upsert pela chave natural, lista
explícita de campos que o robô sobrescreve, `flush()` após criar,
`COMMIT_EVERY=500`, entrypoint `--ano/--dry-run/--limit`.

Agendamento (espelho do de emendas em `scrappers.cron`):

- job diário incremental para o ano corrente (valores e glosas mudam
  retroativamente o ano todo);
- `scripts/backfill_cota.py`: chunks por ano×casa 2022→ano corrente, cada chunk
  em subprocesso isolado, estado em JSON + `flock`, burst `@reboot`,
  auto-encerra e vira no-op;
- tudo via `docker/run-cron-job.sh`.

Sem chave de API nem rate limit relevante: são 1 download por ano×casa.

### API

Router `api/routers/expenses.py`, prefixo `/expenses`, auth padrão, gate
`cota_access = feature_access("cota_parlamentar")` em `api/feature_gate.py`:

- `GET /expenses/summary?parliamentarian_id&year` → `{year_total, monthly:
  [{month, expense_type, total}], top_suppliers: [{supplier_name, supplier_id,
  total, count}]}` (top 10). **403 quando a flag bloqueia** — o agregado é o
  produto (regra do `/amendments/summary`).
- `GET /expenses/?parliamentarian_id&year&month&limit&offset&sort_by&sort_order`
  → lista detalhada; `PREVIEW_ROWS=3` com filtros ignorados quando
  `access.full` é falso; desempate por `id`; `limit` default 50, máx 200.

`Decimal` serializado como string via `field_serializer`; schemas no próprio
router; `/summary` declarado antes de `/`.

### UI

- Registro `cota_parlamentar` em `ui/src/lib/featureFlags.ts` (sem migration).
- Aba **GASTOS** no `ParlamentarDashboard`, spread condicional idêntico ao de
  EMENDAS (`useFeatureAccess` tri-valor + `PaywallOverlay`).
- `ui/src/components/dashboard/GastosTab.tsx`: seletor de ano, gráfico de
  barras empilhadas mês×tipo (recharts + wrapper `ui/components/ui/chart.tsx`),
  top fornecedores, tabela detalhada com link do documento via
  `getSafeExternalUrl`. Estados loading/erro/vazio explícitos, `formatBRL`,
  `'—'` para ausente.
- Client em `ui/src/api/endpoints.ts` + tipos em `ui/src/api/types.ts`.

### Testes

- pytest scrappers: parse dos dois formatos (fixtures reais reduzidas), upsert
  idempotente, fallback de `source_key`, mapeamento de categoria do Senado,
  linhas sem `ideCadastro`.
- pytest API: agregação mensal/fornecedores, gate 403 no summary, preview de 3
  linhas na lista, paginação estável.
- vitest UI: estados do `GastosTab`, gate da aba.
- `scripts/check_ui_api_contract.py` cobre as rotas novas no CI.

## Critérios da task × este design

- Fontes mapeadas com campos, cobertura e limites → seção de levantamento.
- Gastos coletados com carga histórica definida → 2022→hoje, backfill + diário.
- Perfil exibe gasto mensal por tipo e principais fornecedores → aba GASTOS.
- Link para documento fiscal quando a fonte publicar → Câmara PDF direto;
  Senado página oficial de detalhe (comprovante a 1 clique) — limitação da
  fonte documentada acima.
- Cobertura do Senado explicitada → **implementada**.
