# Candidatos do TSE no Mamute (CS-16) — Design

Data: 2026-08-08 · Task: [CS-16](https://lvdev.atlassian.net/browse/CS-16) · Épico: CS-11

## Objetivo

Ter as candidaturas da Eleição Geral de 2026 (federais e estaduais) na base do
Mamute antes do início da campanha (~16/08), preparando o monitoramento futuro
de candidatos — inclusive para a versão estadual do produto.

## Decisões tomadas com o Luiz (2026-08-07/08)

| Decisão | Escolha |
|---|---|
| Modelagem | Tabela própria `candidacy`, FK opcional para `parliamentarian` |
| Fonte | API DivulgaCandContas (`divulgacandcontas.tse.jus.br/divulga/rest/v1`) |
| Escopo de cargos | Todos os titulares: presidente, governador, senador, dep. federal/estadual/distrital. Sem vices/suplentes |
| Cadência | Cron diário no container de scrappers, upsert idempotente |
| Escopo de UI | Nenhum nesta entrega — somente banco de dados |
| Estratégia de coleta | Incremental: listagem sempre; detalhe só para candidatura nova ou alterada |

## Fatos validados ao vivo (2026-08-07)

- `/eleicao/ordinarias` → Eleição Geral Federal 2026 = id `20322002026`, pleito 2026-10-04.
- Listagem `/candidatura/listar/{ano}/{uf}/{idEleicao}/{codCargo}/candidatos`
  já devolve candidaturas ("Aguardando julgamento") com `id`, `nomeUrna`,
  `numero`, `nomeCompleto`, `tituloEleitor`, `descricaoSituacao`,
  `descricaoTotalizacao`, `partido`. **CPF vem nulo na listagem.**
- Detalhe `/candidatura/buscar/{ano}/{uf}/{idEleicao}/candidato/{id}` traz
  `cpf` preenchido, `fotoUrl`, `dataUltimaAtualizacao`.
- Na base de produção: 557/557 deputados têm CPF; 0/87 senadores têm.

## Modelo de dados

Tabela nova `candidacy` (migração Alembic; nenhuma tabela existente muda, exceto
o relationship `candidacies` em `Parliamentarian`):

- `id` BigInteger PK
- `election_year` Integer NOT NULL + `tse_candidate_id` BigInteger NOT NULL —
  chave natural, unique composto `uq_candidacy_election_tse_id`
- `office_code` Integer (1 presidente, 3 governador, 5 senador, 6 dep. federal,
  7 dep. estadual, 8 dep. distrital), `office` Text
- `state` Text — UF da candidatura, `BR` para presidente
- `ballot_number` Integer, `ballot_name` Text, `full_name` Text
- `party` Text, `coalition` Text
- `status` Text (`descricaoSituacao`), `totalization_status` Text
  (`descricaoTotalizacao`)
- `cpf` Text, `voter_id` Text, `photo_url` Text, `tse_last_update` DateTime —
  vindos do detalhe
- `listing_fingerprint` Text — hash dos campos da listagem; só é gravado após
  upsert completo com detalhe, de modo que falha no detalhe força nova
  tentativa na execução seguinte
- `parliamentarian_id` BigInteger FK → `parliamentarian.id`, `ON DELETE SET
  NULL` (candidatura é fato público; não some com o parlamentar — mesma decisão
  de `parliamentary_amendment`)
- `match_status` Text NOT NULL — `matched_cpf` / `matched_name` / `ambiguous` /
  `unmatched` / `manual` (reservado para correção humana futura)
- `details` JSONB — payload bruto do detalhe, por fidelidade
- `created_at` / `updated_at`

Índices: `state`, `office_code`, `match_status`, `parliamentarian_id`.

## Crawler — `mamute_scrappers/tse_crawler/`

Espelha o `portal_crawler`:

- **`client.py`** — `DivulgaCandClient`: timeout, retry com backoff em
  falha transitória, throttle entre requests. Falha persistente de uma
  **listagem** é ruidosa (`IncompleteListingError`, exit != 0) — truncar em
  silêncio foi o bug das emendas 2022. Falha persistente de um **detalhe**
  apenas loga e segue: o registro fica sem fingerprint e é retomado no dia
  seguinte.
- **`parsing.py`** — coerção de texto, CPF normalizado (11 dígitos),
  `parse_tse_datetime`, `compute_listing_fingerprint`, montagem de payloads.
- **`matching.py`** — cascata determinística, sem fuzzy (mesma filosofia do
  `author_matching`): (1) CPF normalizado igual → `matched_cpf`; (2) nome
  completo/urna normalizado igual a `full_name`/`name` de parlamentar —
  1 hit → `matched_name`; >1 hit, desempata por UF (`state_elected` ==
  `state` da candidatura); persiste >1 → `ambiguous`; 0 → `unmatched`.
  `manual` nunca é sobrescrito pelo robô.
- **`candidacy.py`** — comando (`python -m mamute_scrappers.tse_crawler.candidacy`):
  1. Carrega `.env` antes de tocar no banco (lição da PR #160).
  2. Resolve o id da eleição pelo ano em `/eleicao/ordinarias`
     (`tipoAbrangencia == "F"`); nada de id hardcoded.
  3. Varre listagens UF×cargo: presidente em `BR`; governador/senador/dep.
     federal nas 27 UFs; dep. estadual nas 26 (sem DF); dep. distrital só DF —
     ≈ 136 requests/execução.
  4. Para cada candidato: fingerprint da listagem; se novo ou mudou → busca
     detalhe, casa com parlamentar, upsert completo; sem mudança → não toca.
  5. Commit parcial a cada 200 upserts (retomável, como nas emendas).
  6. Flags: `--ano` (default: ano corrente), `--dry-run`, `--limit`,
     `--max-details` (teto de detalhes por execução; o excedente fica sem
     fingerprint e é retomado depois).

Volumetria: carga inicial ~29k detalhes com throttle 0.5s ≈ 4h (rodada manual
única); diário incremental ~136 listagens + dezenas de detalhes.

Candidatura que sumir da listagem **não é deletada** — histórico fica; situação
muda pelo próprio TSE (indeferido/cassado/renúncia).

## Operação

- Cron diário em `mamute_scrappers/docker/scrappers.cron` via
  `run-cron-job.sh` (lock contra execução concorrente), fora dos horários de
  pico dos outros crawlers.
- Carga inicial manual documentada na PR (comando + duração esperada).
- Sem variável de ambiente nova: a API DivulgaCandContas não usa chave.

## Testes

`mamute_scrappers/tests/`, no padrão dos existentes (fixtures JSON reais,
SQLite em memória com modelos-espelho):

- `test_tse_client.py` — retry/backoff, listagem ruidosa vs detalhe tolerante.
- `test_tse_parsing.py` — fingerprint estável/sensível, CPF, datas, payloads.
- `test_tse_matching.py` — CPF, nome (senador sem CPF), desempate por UF,
  ambíguo, não casado, `manual` preservado.
- `test_tse_candidacy_upsert.py` — idempotência, detalhe ausente → fingerprint
  nulo → refetch, repetição no mesmo lote.

## Fora de escopo (explícito)

- Qualquer mudança de UI ou API HTTP.
- Monitoramento/favoritar candidatos não-parlamentares (vem com a versão
  estadual).
- Fotos como binário (guardamos só a URL), bens, prestação de contas.
