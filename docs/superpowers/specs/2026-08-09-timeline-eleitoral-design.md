# Timeline eleitoral do político (CS-54) — Design

Data: 2026-08-09 · Task: [CS-54](https://lvdev.atlassian.net/browse/CS-54) · Épico: CS-11
Base: candidaturas 2026 da CS-16 (`candidacy` + `tse_crawler`), já em produção.

## Objetivo

Backend da linha do tempo eleitoral de cada político: todas as disputas
(ano, cargo, UF/município, partido, resultado) com o patrimônio declarado em
cada eleição — consumível tanto pela futura tela de candidatos quanto pela
tela do político. Somente backend nesta entrega (banco + coleta + endpoint
REST); UI fica para task futura.

## Decisões tomadas com o Luiz (2026-08-09)

| Decisão | Escolha |
|---|---|
| Patrimônio histórico | Para **todos** os candidatos (~11.7k→29k), não só parlamentares |
| Parlamentares sem candidatura 2026 (~200) | Incluídos já, via varredura das gerais 2018/2022 |
| Entrega | Banco + coleta + **endpoint REST** pronto para a UI |
| Abordagem | Tabela normalizada `electoral_history` + pipeline de sementes |

## Fatos validados (produção + API, 2026-08-09)

- `candidacy.details` (JSONB, já armazenado para 100% das candidaturas 2026)
  contém **`eleicoesAnteriores`**: lista completa das disputas da pessoa —
  ano, cargo, sgUe, local, partido, nomeUrna, nomeCandidato, nrCandidato,
  `situacaoTotalizacao` (Eleito/Não eleito/Concorrendo/…), `txLink` (página
  oficial do TSE) e os ids (`idEleicao` + `id`) para buscar o detalhe daquele
  ano. Inclui eleições municipais e a própria 2026.
- `candidacy.details` também contém **`bens`** (lista) e o total (ex.: Sergio
  Moro 2026: 12 bens, R$ 1.036.642,25) — patrimônio 2026 já está local.
- O patrimônio das eleições passadas sai do mesmo endpoint de detalhe
  (`/candidatura/buscar/{ano}/{sgUe}/{idEleicao}/candidato/{id}`), 1 request
  por candidatura antiga.
- Todo parlamentar em exercício disputou uma eleição geral em 2018 ou 2022 —
  logo as listagens dessas eleições (~550 requests) alcançam os ~200 sem
  candidatura 2026, e o `eleicoesAnteriores` do detalhe encontrado traz o
  histórico completo (municipais incluídas, que seriam inviáveis de varrer:
  5.570 municípios).

## Modelo de dados

Tabela nova `electoral_history` — 1 linha por pessoa × eleição × cargo:

- `id` BigInteger PK
- `election_year` Integer NOT NULL + `tse_candidate_id` BigInteger NOT NULL —
  chave natural (unique `uq_electoral_history_year_tse_id`); o id é o da
  pessoa NAQUELA eleição (muda a cada ano)
- `tse_election_id` BigInteger (`idEleicao`)
- `parliamentarian_id` BigInteger FK → parliamentarian, `ON DELETE SET NULL`,
  nullable — denormalizado em todas as linhas da pessoa
- `candidacy_id` BigInteger FK → candidacy (a candidatura 2026 que originou a
  timeline), `ON DELETE SET NULL`, nullable
- `office` Text, `state` Text (`sgUe` verbatim; em municipais é o código do
  município), `locality` Text (`local`: nome legível, ex.: cidade)
- `party` Text, `ballot_name` Text, `full_name` Text, `ballot_number` Integer
- `result` Text (`situacaoTotalizacao`)
- `declared_assets` Numeric(18,2) nullable, `assets_count` Integer nullable,
  `assets` JSONB nullable
- `assets_fetched_at` DateTime nullable — NULL = patrimônio pendente de
  busca; controla o incremental (papel análogo ao fingerprint da CS-16)
- `source_link` Text (`txLink`)
- `created_at` / `updated_at`

Índices: `parliamentarian_id`, `candidacy_id`, `election_year`. Relationships
novos em `Parliamentarian` e `Candidacy`; nenhuma coluna existente muda.

Espelho do modelo também em `api/db/models/` (a API tem modelos próprios).

## Pipeline de coleta — `tse_crawler/electoral_history.py`

Comando único com três fases, idempotente e retomável; roda em cron diário
próprio (`tse-electoral-history`, com lock via `run-cron-job.sh`, horário
afastado do `tse-candidacies`):

1. **Semear dos locais (zero API):** varre `candidacy` 2026 com `details`
   preenchido, parseia `eleicoesAnteriores` e faz upsert do esqueleto
   (disputa + resultado + link), herdando `candidacy_id` e
   `parliamentarian_id`. Re-roda sempre — barato — então `result` acompanha o
   TSE sozinho (Concorrendo → Eleito/Não eleito na apuração) e candidaturas
   2026 novas (registro até 15/08) ganham timeline automaticamente.
2. **Semear parlamentares sem candidatura 2026:** para quem não tem linha em
   `electoral_history` via candidacy, varre as listagens das gerais 2022 e
   2018 (~550 requests, cache em memória na execução), casa pela cascata da
   CS-16 (nome+UF; confirmação por CPF via detalhe quando o parlamentar tem
   CPF), busca o detalhe da candidatura encontrada e semeia a timeline
   completa a partir do `eleicoesAnteriores` dele.
3. **Enriquecer patrimônio:** linhas com `assets_fetched_at` NULL → busca o
   detalhe daquele ano/eleição, grava `declared_assets` (total), `assets_count`
   e `assets` (lista), marca `assets_fetched_at`. `--max-details` limita por
   execução; o cron drena ao longo dos dias (~30-50k detalhes estimados).
   Falha de detalhe → continua NULL → retenta na próxima execução.

Reuso integral do `DivulgaCandClient` (retry assimétrico) e do
`matching`/`parsing` da CS-16. Entrada malformada de `eleicoesAnteriores`
(sem ano ou sem id) é pulada com log, nunca derruba a execução. Linhas nunca
são deletadas pelo robô.

Flags: `--dry-run`, `--max-details`, `--skip-seed` (só drenar bens),
`--parliamentarians-only` (fases 1-2 sem fase 3, para semear rápido).

## Endpoint REST

Na API FastAPI existente, seguindo o padrão de autenticação e formato dos
routers atuais:

- `GET /parliamentarians/{id}/electoral-history` — timeline do político.
- `GET /candidacies/{id}/electoral-history` — timeline pela candidatura 2026.
- Resposta: `{ "entries": [ { "year", "office", "state", "locality",
  "party", "ballot_name", "result", "declared_assets", "assets_count",
  "source_link" } ] }`, ordenada por ano desc. A lista completa de bens
  (`assets`) só entra com `?include_assets=true`.
- 404 quando o político/candidatura não existe; lista vazia quando existe mas
  ainda não tem timeline coletada.

## Testes

- Parser de `eleicoesAnteriores` com fixture real (amostra do Sergio Moro).
- Upsert idempotente em SQLite-espelho (padrão `test_tse_candidacy_upsert`).
- Semeadura: candidacy → linhas de esqueleto; entrada malformada pulada.
- Fase 3: linha sem `assets_fetched_at` recebe bens; falha de detalhe mantém
  NULL.
- Endpoints: casos 200 (com e sem `include_assets`), 404 e lista vazia, no
  padrão de `api/tests/`.

## Fora de escopo (explícito)

- Qualquer UI (tela de candidatos e tela do político consomem depois).
- Notificação de eleito (fica na CS-13; esta base a viabiliza via `result`).
- Prestação de contas de campanha (receitas/despesas) — só bens declarados.
- Histórico de quem não é parlamentar nem candidato 2026.
