# Emendas parlamentares no perfil do parlamentar (CS-17)

- **Jira:** [CS-17](https://lvdev.atlassian.net/browse/CS-17) — épico CS-11 (Mamute Político)
- **Data:** 2026-08-06
- **Status:** aprovado, aguardando implementação

## Problema

Emendas parlamentares — o dinheiro do orçamento federal que cada parlamentar
destina — são dado central de transparência e hoje não existem no Mamute. O
usuário consegue ver o que um deputado propôs, votou e falou, mas não para onde
ele mandou verba.

## Escopo

Coletar emendas **de autoria individual** a partir de 2022, associá-las aos
parlamentares já cadastrados e exibi-las no perfil (`/parlamentar/:id`).

Fora de escopo nesta entrega: emendas de bancada, de comissão e de relator;
telas agregadas fora do perfil; emendas no índice do chatbot.

## Desambiguação obrigatória

"Emenda parlamentar" aqui é **emenda orçamentária** (destinação de verba). Não
confundir com "emenda a proposição" (alteração de texto de projeto de lei), que
o repositório já toca via `proposition_type`. São dados distintos, de fontes
distintas, e este documento trata apenas da primeira.

## Fonte de dados

Fonte **única**: Portal da Transparência.

```
GET https://api.portaldatransparencia.gov.br/api-de-dados/emendas
    ?ano=<int>&pagina=<int>
    header: chave-api-dados: <PORTAL_TRANSPARENCIA_API_KEY>
```

A descrição do ticket menciona "APIs do governo federal, da Câmara e do Senado".
Isso não se confirma:

| Fonte | Serve emenda orçamentária? |
|---|---|
| Portal da Transparência | Sim — fonte real |
| Câmara `dadosabertos` v2 | Não tem endpoint de emenda orçamentária |
| Senado / Siga Brasil | Painel web, sem API REST utilizável por crawler |

### Contrato de resposta (verificado no OpenAPI em 2026-08-06)

`codigoEmenda`, `ano`, `tipoEmenda`, `autor`, `nomeAutor`, `numeroEmenda`,
`localidadeDoGasto`, `funcao`, `subfuncao`, `valorEmpenhado`, `valorLiquidado`,
`valorPago`, `valorRestoInscrito`, `valorRestoCancelado`, `valorRestoPago`.

Três propriedades desse contrato definem o desenho inteiro:

1. **Não existe identificador de parlamentar.** O autor vem só como texto
   (`nomeAutor`). Nossa base casa por `parliamentarian_code`. O "cruzar com a
   base" do ticket é, na prática, um problema de casamento por nome.
2. **Todos os valores são `string`** em formato brasileiro (`"1.000.000,00"`).
3. **Os valores mudam ao longo do ano** (empenhado → liquidado → pago). O
   registro não é imutável: exige upsert periódico, não insert único.

### Credencial

Nova variável `PORTAL_TRANSPARENCIA_API_KEY`, declarada em
`mamute_scrappers/.env.example` e preenchida no `.env` do container de
scrappers. A API e o chatbot não falam com o Portal e não recebem a chave.

Obtenção: cadastro gratuito por e-mail em
`portaldatransparencia.gov.br/api-de-dados/cadastrar-email`.

O rate limit é por chave, na casa de 30 requisições/minuto fora da madrugada e
90 durante ela. Isso torna a coleta um trabalho de cron, nunca sob demanda.

## Modelo de dados

Tabela nova `parliamentary_amendment`:

| Coluna | Tipo | Observação |
|---|---|---|
| `id` | BigInteger PK | |
| `amendment_code` | Text UNIQUE | `codigoEmenda` — chave natural do Portal |
| `year` | Integer | |
| `amendment_number` | Text | `numeroEmenda` |
| `amendment_type` | Text | `tipoEmenda` |
| `author_name_raw` | Text | `nomeAutor`, preservado como veio |
| `author_raw` | Text | `autor`, preservado como veio |
| `parliamentarian_id` | BigInteger FK nullable | `ON DELETE SET NULL` |
| `match_status` | Text | `matched` \| `unmatched` \| `ambiguous` \| `manual` |
| `spending_locality` | Text | `localidadeDoGasto` |
| `function`, `subfunction` | Text | |
| `committed_value` | Numeric(18,2) | `valorEmpenhado` |
| `settled_value` | Numeric(18,2) | `valorLiquidado` |
| `paid_value` | Numeric(18,2) | `valorPago` |
| `remainder_inscribed` | Numeric(18,2) | `valorRestoInscrito` |
| `remainder_cancelled` | Numeric(18,2) | `valorRestoCancelado` |
| `remainder_paid` | Numeric(18,2) | `valorRestoPago` |
| `created_at`, `updated_at` | DateTime tz | padrão do repositório |

Índices: `UNIQUE(amendment_code)`; `(parliamentarian_id, year)` para as consultas
do perfil; `(match_status)` para o painel de auditoria.

O modelo é espelhado em `mamute_scrappers/db/models/` e `api/db/models/`, como
todas as outras tabelas do projeto.

### Três decisões que divergem do padrão do repositório

**`ON DELETE SET NULL` em vez de CASCADE.** As demais tabelas ligadas a
parlamentar (`plenary_attendance`, `roll_call_votes`, `speeches_transcripts`)
usam CASCADE. Aqui não: a emenda é fato orçamentário público e não deve
desaparecer se o parlamentar sair da base.

**`Numeric(18,2)` em vez de Text.** O Portal entrega string; a conversão
acontece na ingestão. É o que permite somar no banco para o resumo do perfil,
em vez de somar no cliente.

**`match_status` explícito** em vez de inferir estado por
`parliamentarian_id IS NULL`. "Ninguém casou" e "casou com dois e não soube
escolher" são situações diferentes, e o painel de auditoria precisa
distingui-las.

## Casamento autor → parlamentar

Módulo isolado `mamute_scrappers/portal_crawler/author_matching.py`, sem
dependência de rede, testável com fixtures.

Entrada: `nomeAutor`, `ano`. Saída: `(parliamentarian_id | None, match_status)`.

Cascata determinística, aplicada apenas a emendas de tipo individual:

1. Normalizar: NFKD sem diacríticos, minúsculas, espaços colapsados. A função
   `_normalize_text` de `camara_crawler/plenary_attendance.py:92` já faz
   exatamente isso e é o ponto de partida.
2. Casamento exato por `parliamentarian.name` normalizado → `matched`.
3. Casamento exato por `parliamentarian.full_name` normalizado → `matched`.
4. Nenhum candidato → `unmatched`. Dois ou mais → `ambiguous`.

O casamento roda contra a base inteira de parlamentares, sem recorte por
mandato. Restringir candidatos ao mandato vigente no ano da emenda parece
natural, mas exigiria derivar períodos de mandato — que na Câmara moram no
`details` JSONB e no Senado saem de `_collect_mandato_legislatura_periods`, com
formatos distintos. É complexidade real para resolver um problema que talvez
não exista. O recorte por ano fica reservado como critério de desempate quando
a fatia diagnóstica mostrar volume relevante de `ambiguous`; se homônimo não
aparecer nos dados, não se escreve o código.

**Não há casamento aproximado automático.** Fuzzy silencioso em produto de
transparência atribui dinheiro público à pessoa errada, e o erro é invisível
justamente porque é silencioso. Casamento aproximado pode entrar depois como
*sugestão* no painel de administração, revisada por humano, gravando
`match_status = 'manual'` — nunca como escrita automática.

### Emendas não casadas

Toda emenda individual é persistida, casando ou não. As não casadas ficam com
`parliamentarian_id` nulo e aparecem no painel de administração agrupadas por
`author_name_raw`, com contagem e soma de valores. Descartar seria perder
visibilidade de quanto ficou de fora — inaceitável num produto de transparência.

## Coleta

### Crawler incremental

`mamute_scrappers/portal_crawler/emendas.py`, no molde de
`camara_crawler/plenary_attendance.py`: argumentos `--ano` (padrão: ano
corrente), `--dry-run` e `--interactive`; upsert idempotente por
`amendment_code`; log final com contagem de `matched` / `unmatched` /
`ambiguous`.

Regra de reprocessamento: os valores financeiros são sempre atualizados, mas
`parliamentarian_id` **não** é sobrescrito quando `match_status == 'manual'`.
Correção humana prevalece sobre o robô.

### Backfill 2022 → ano corrente

`mamute_scrappers/scripts/backfill_emendas.py`, no molde de
`scripts/backfill_propositions.py`: arquivo de estado JSON, trava `flock`,
`--chunks-per-run`, `--status`, e encerramento automático quando a fila zera.

Cada chunk é um ano, portanto são cerca de cinco chunks. A fila esvazia em uma
tarde, não em dias como o backfill de proposições.

### Agendamento

Minutos escolhidos para não colidir com os dezoito jobs já existentes em
`mamute_scrappers/docker/scrappers.cron`:

```cron
# Emendas parlamentares — ano corrente (diário, 06h50 UTC)
50 6 * * *  ... python -m mamute_scrappers.portal_crawler.emendas --ano $(date +\%Y)

# Backfill 2022 → corrente (a cada 1h no minuto 35; auto-encerra)
35 * * * *  ... python -m mamute_scrappers.scripts.backfill_emendas --chunks-per-run 2
```

Mais um `@reboot` de burst, como fazem os demais backfills.

O job incremental diário continua necessário depois que o backfill encerra:
`valorPago` do ano corrente muda durante o ano inteiro.

## API

Router novo `api/routers/amendments.py`, registrado em `api/main.py`.

| Rota | Retorno |
|---|---|
| `GET /amendments?parliamentarian_id=&year=&sort_by=&sort_order=&limit=&offset=` | Lista paginada, no molde de `/roll-call-votes` |
| `GET /amendments/summary?parliamentarian_id=&year=` | `{year, count, committed_total, paid_total}` |

O resumo fica sob `/amendments`, e não sob `/parliamentarians/{id}/…`, por dois
motivos: mantém tudo sobre emenda num arquivo só, e o verificador de contrato do
CI (`scripts/check_ui_api_contract.py`) casa rota pelo prefixo declarado no
`APIRouter` — pendurar a rota noutro router exigiria cirurgia em
`parliamentarians.py`, que já tem 546 linhas.

A rota de auditoria fica em `api/routers/admin.py`, não no router novo:
`GET /admin/amendments/unmatched`, retornando autores não casados agrupados por
`author_name_raw` com contagem e soma. Todas as rotas `/admin` moram nesse
arquivo e herdam dele o gate de administrador; abrir uma exceção só porque o
assunto é emenda espalharia a regra de acesso por dois lugares.

O DTO `ProjectDashboardStatsOut` (`api/routers/projects.py:112`) **não é
alterado**. Aquele objeto descreve uma janela fixa de três meses; emenda é
grandeza de ano civil. Misturar as duas semânticas no mesmo DTO cria uma
armadilha para quem mexer depois. O resumo anual tem endpoint próprio.


## Interface

**Aba nova.** `TabsTrigger value="emendas"` no bloco "Atividades do
Parlamentar" de `ui/src/pages/ParlamentarDashboard.tsx:216`, ao lado de
VOTAÇÕES / PROPOSIÇÕES / TAQUIGRÁFICAS. Conteúdo em
`ui/src/components/dashboard/EmendasTable.tsx`, no molde de `VotacoesTable.tsx`
(filtros, ordenação, paginação). Colunas: número, localidade do gasto, função,
valor empenhado, valor pago.

**Resumo no card de estatísticas.** `EstatisticasCard` hoje é uma fileira de
quatro círculos de 49 px; um valor monetário como `R$ 12,5 mi` não cabe nesse
formato. O resumo entra como bloco separado abaixo dos círculos, com divisória,
exibindo "Emendas <ano> — Destinado / Pago". O componente recebe uma prop nova
`amendmentsSummary`, independente de `stats`, coerente com a separação de
endpoints descrita acima.

**Painel administrativo.** Rota `/admin/emendas-nao-casadas` mais um card em
`ui/src/pages/AdminPage.tsx`, listando autores não casados por volume, para
auditoria e correção.

Clientes novos em `ui/src/api/endpoints.ts`: `listAmendments` e
`getParliamentarianAmendmentsSummary`.

## Testes

| Arquivo | Cobre |
|---|---|
| `test_emendas_author_matching.py` | Cascata de casamento com fixtures de nomes reais: acentuação, sufixos, nome de guerra versus nome civil, homônimo gerando `ambiguous` |
| `test_emendas_value_parsing.py` | `"1.000.000,00"` → `Decimal("1000000.00")`; vazio e nulo |
| `test_emendas_upsert.py` | Idempotência do upsert e preservação de `match_status = 'manual'` |
| `test_amendments_api.py` | Lista, filtro por parlamentar e ano, resumo |
| `EmendasTable.test.tsx` | Renderização, estado vazio, formatação monetária |

Nenhum teste de casamento depende de rede.

## Riscos

**Taxa de casamento desconhecida.** O Portal pode publicar nome civil onde a
nossa base guarda nome parlamentar. Se a taxa for baixa, o painel de auditoria
deixa de ser conveniência e vira pré-requisito. Por isso a primeira fatia da
implementação é diagnóstica.

**Valores literais de `tipoEmenda` desconhecidos.** O OpenAPI declara o campo
como string livre, sem enumerar valores. O filtro de "individual" só pode ser
escrito depois de observar uma resposta real, o que exige a chave.

**Rate limit do Portal.** Mitigado por atraso conservador entre requisições e
por rodar em cron, fora de horário de pico.

## Ordem de entrega

1. **Diagnóstico.** Chave, crawler em `--dry-run` e módulo de casamento.
   Entrega um número: a taxa real de casamento, e os valores literais de
   `tipoEmenda`. Decide o peso das fatias seguintes.
2. Modelo, migration, persistência e cron incremental.
3. Backfill 2022 → corrente.
4. API: lista, resumo e rota administrativa.
5. Interface: aba, tabela e resumo no card.
6. Painel administrativo de não casadas.

A primeira fatia é deliberadamente diagnóstica em vez de entregável. Construir
aba e card antes de saber se o dado casa é construir em cima de suposição.
