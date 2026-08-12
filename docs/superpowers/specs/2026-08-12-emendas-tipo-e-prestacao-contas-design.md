# Emendas: rótulo de tipo e prestação de contas no Transferegov (CS-56) — Design

Data: 2026-08-12 · CS-56 · Épico CS-11 · PR 2 de 2 (depende da PR de feature
flags, ver `2026-08-12-feature-flags-design.md`)

## Objetivo

Feedback de usuário jornalista, em duas partes:

1. Rotular cada emenda pelo tipo, para a leitura da tabela não exigir
   conhecimento prévio de orçamento — em particular identificar a "emenda Pix".
2. Linkar a prestação de contas da emenda. O ente que recebe é obrigado a
   prestar contas no Transferegov, e nenhuma plataforma expõe isso hoje. É o
   diferencial competitivo da task.

## Levantamento da fonte (medido em 2026-08-12)

### O que existe na nossa base

| `amendment_type` | Qtd | Rótulo na tela |
|---|---|---|
| Emenda Individual - Transferências com Finalidade Definida | 24.910 (85%) | `Finalidade definida` |
| Emenda Individual - Transferências Especiais | 4.254 (15%) | `Pix` |

São os dois únicos valores em produção (2022–2026). O `amendment_type` **já é
coletado, já está no banco e já sai em `AmendmentOut`** — a parte (1) não exige
coleta nenhuma, só exibição.

### O que o Transferegov entrega

A API pública `https://api.transferegov.gestao.gov.br/transferenciasespeciais/`
(PostgREST, sem chave) tem `plano_acao_especial`, cujo campo
`numero_emenda_parlamentar_plano_acao` **é exatamente o nosso `amendment_code`**.

Amostra aleatória de 300 emendas Pix:

| Fato | Medido |
|---|---|
| Emendas com plano de ação na fonte | **300/300 (100%)** |
| Planos por emenda | mediana **8**, média 13,1, máximo 100 |
| Total de planos na fonte | 57.827 |
| Planos com prestação de contas | 44,2% |
| **Emendas com ao menos 1 plano prestando contas** | **77,3%** |

**A relação é 1:N, não 1:1.** Uma emenda Pix se desdobra em vários planos de
ação, um por ente beneficiário. A tela não exibe "o plano da emenda", exibe uma
lista de beneficiários.

A prestação de contas vive em duas tabelas da fonte:

- `relatorio_gestao_novo_especial` — o regime atual. 42,8% dos planos. Traz
  `tipo` (Parcial/Final), `situacao`, `valor_executado`, `valor_pendente`, data.
- `relatorio_gestao_especial` — o legado. 6,4%, seca a partir de 2025.

União das duas: 44,2%.

### Cobertura por ano — o dado que define a linguagem da tela

| Ano do plano | Com prestação |
|---|---|
| 2022 | 58% |
| 2023 | 57% |
| 2024 | 56% |
| 2025 | 46% |
| 2026 | **6%** |

Ausência de prestação **não é sonegação**: no ano corrente o prazo ainda está
aberto. Ver "Linguagem da tela".

### Por que as outras 85% ficam de fora

Duas tentativas, ambas medidas e descartadas:

- **API do Transferegov para Discricionárias e Legais:** não existe. O
  cronograma oficial prevê a 1ª entrega (atos preparatórios) entre 07/2026 e
  10/2026, e instrumentos só em 2027.
- **Dump CSV do SICONV** (`repositorio.dados.gov.br/seges/detru/siconv_emenda.csv.zip`,
  297 mil linhas): a chave `NR_EMENDA` é autor(4)+sequencial(4), **sem o ano**,
  enquanto nosso `amendment_code` tem ano. A emenda 0019/2022 e a 0019/2023 do
  mesmo deputado colidem na mesma chave. Testado em 40 emendas: o nome do
  parlamentar bate quase sempre (a chave está certa), mas desambiguar o ano só
  funcionou em **11/40 (28%)**, e 8 não tinham linha nenhuma.

Publicar "a prestação de contas desta emenda" com 28% de casamento ambíguo, num
produto de jornalismo, é gerar acusação falsa. **Fora de escopo.**

## Decisões tomadas com o Luiz (2026-08-12)

| Decisão | Escolha |
|---|---|
| Ambição | Ingerir do Transferegov e exibir o status da prestação, não só linkar |
| Forma na tela | Linha expansível com os beneficiários inline |
| Rótulos | `Pix` e `Finalidade definida`, com o nome oficial no tooltip |
| Linha "Finalidade definida" | "Não disponível" + link à consulta geral do portal |
| SICONV | Fora de escopo (28% de casamento, não publicável) |
| Feature flag | `emendas_prestacao`, nascendo em `off` |

## Arquitetura

### 1. Banco — `amendment_action_plan`

Migration encadeada a partir do head da PR de feature flags. ~58 mil linhas.

```
id_plano_acao              bigint      PK   -- chave natural da fonte
codigo_plano_acao          text
amendment_code             text        FK -> parliamentary_amendment.amendment_code,
                                             ON DELETE SET NULL, indexado
ano                        integer
situacao                   text             -- CIENTE | IMPEDIDO | IMPEDIDO_REJEICAO_PLANO_TRABALHO
beneficiario_nome          text
beneficiario_cnpj          text
beneficiario_uf            text
valor_custeio              numeric(18,2)
valor_investimento         numeric(18,2)
-- prestação de contas, desnormalizada:
prestacao_situacao         text             -- DISPONIBILIZADO | EM_ELABORACAO | ENVIADO_PARA_ANALISE | NULL
prestacao_tipo             text             -- Parcial | Final | NULL
prestacao_valor_executado  numeric(18,2)
prestacao_valor_pendente   numeric(18,2)
prestacao_data             timestamptz
prestacao_origem           text             -- 'novo' | 'legado' | NULL
created_at, updated_at     timestamptz
```

`ON DELETE SET NULL` no `amendment_code` segue a política já adotada em
`parliamentary_amendment.parliamentarian_id`: o plano de ação é fato público e
não deve sumir se a emenda sair da base.

**Por que a prestação é desnormalizada:** a fonte tem 1,02 relatório por plano
(1.725 relatórios para 1.685 planos). Guardamos o mais forte, com a regra
documentada no módulo: **`Final` vence `Parcial`; empatado no tipo, vence o mais
recente por data; `relatorio_gestao_novo_especial` vence o legado.** Uma tabela,
um join, sem histórico que ninguém vai ler. Se um dia quisermos série temporal,
a migration é aditiva.

Valores monetários em `Numeric(18,2)`, nunca float — mesma política do resto do
projeto (dinheiro público não perde centavo em ponto flutuante).

### 2. Coleta — `mamute_scrappers/transferegov_crawler/`

Pacote novo, no mesmo formato de `portal_crawler`/`tse_crawler`:

- `client.py` — cliente PostgREST com paginação por `limit`/`offset` e
  `Prefer: count=exact`. Sem chave de API.
- `action_plans.py` — busca os planos, busca os dois tipos de relatório, aplica
  a regra de precedência acima, e faz upsert idempotente por `id_plano_acao`.
  Commit parcial a cada 500 linhas, como em `emendas.py`.

O `amendment_code` do plano é gravado como veio; planos cujo código não existe
em `parliamentary_amendment` são gravados mesmo assim com o FK nulo (a coleta do
Portal pode estar atrás), e o total desses vai para o log.

Refaz os ~58k a cada execução — são ~58 requisições paginadas, cabe folgado.

**Cron:** entrada em `mamute_scrappers/docker/scrappers.cron`, diária, logo após
a coleta de emendas (que roda 50 6). O plano de ação depende da emenda existir
para casar, então roda depois.

### 3. API

**`AmendmentOut` ganha um bloco agregado**, calculado com `LEFT JOIN` +
`GROUP BY` na listagem:

```
planos_total            int    -- 0 quando não é Pix ou ainda não coletado
planos_com_prestacao    int
valor_executado_total   str    -- string, como os demais valores monetários
```

**Rota nova:** `GET /amendments/{amendment_code}/action-plans` → lista de planos
com beneficiário, valores e prestação. É o que a linha expandida consome,
carregado **só quando expande** — a listagem não paga o custo de 58k linhas.

A API fica aberta como as demais (a flag controla só a UI, conforme o design de
feature flags).

### 4. UI

**`ui/src/lib/transferegov.ts`** — monta o link para a consulta pública, no
espelho de `lib/portalTransparencia.ts` (que valida o código antes de montar a
URL). Duas consultas: planos de ação (Pix) e portal geral (Finalidade definida).

**`ui/src/components/dashboard/EmendasTable.tsx`:**

- Coluna **Tipo**: badge `Pix` / `Finalidade definida`, com o nome oficial
  completo no `title`.
- Coluna **Prestação**: `5/8` para Pix com planos; "Não disponível" com link ao
  portal para Finalidade definida.
- Linha Pix vira expansível, revelando os beneficiários inline: ente, UF,
  situação da prestação e valor executado.

**O detalhe que vai morder:** hoje o `onClick` da linha inteira abre o Portal da
Transparência, e a linha tem `role="link"` + `onKeyDown` para Enter/Espaço. Com
o clique passando a expandir, isso muda: a linha vira `role="button"` com
`aria-expanded`/`aria-controls`, e o link externo vira um botão dedicado na
coluna da direita (o ícone `ExternalLink` que já existe, agora clicável, com
`stopPropagation`). Emenda sem plano não expande e não recebe `role`.

**Toda a mudança fica atrás de `useFeatureFlag('emendas_prestacao')`, checada
uma única vez dentro do `EmendasTable`**, derivando as colunas. Nada vaza para o
`ParlamentarDashboard`. Com a flag off, a tabela renderiza exatamente como hoje
— inclusive o `onClick` da linha abrindo o Portal.

Entrada nova em `ui/src/lib/featureFlags.ts`:
`emendas_prestacao: { label: 'Prestação de contas das emendas Pix', since: '2026-08-12' }`.

## Linguagem da tela

A tela **nunca diz "não prestou contas"**. A distinção fica no componente, com o
ano do plano como critério, e entra em teste:

| Situação | Texto |
|---|---|
| Plano do ano corrente sem prestação | "sem prestação — prazo aberto" |
| Plano de ano fechado sem prestação | "sem prestação registrada" |
| Com prestação | tipo (Parcial/Final) + valor executado |

## Testes

**Coleta** (`mamute_scrappers/tests/test_transferegov_action_plans.py`):
- Regra de precedência do relatório: `Final` vence `Parcial`; mesmo tipo, vence
  o mais recente; `novo` vence `legado`.
- Upsert idempotente: rodar duas vezes não duplica nem altera.
- Plano com `amendment_code` desconhecido é gravado com FK nula.
- Parsing de valores para `Decimal`, sem float.

**API** (`api/tests/test_amendment_action_plans.py`):
- Agregado correto: emenda com 8 planos e 5 com prestação → `planos_total=8`,
  `planos_com_prestacao=5`.
- Emenda sem plano → zeros, não `null`.
- `valor_executado_total` serializado como string.
- Rota de planos devolve vazio (não 404) para emenda sem plano.

**UI** (Vitest + testing-library):
- Flag off: tabela idêntica à atual, sem coluna Tipo, `onClick` abrindo o Portal.
- Flag on: badge correto por tipo; linha Pix expande e lista beneficiários;
  linha Finalidade definida não expande e mostra "Não disponível".
- **Plano de 2026 sem prestação mostra "prazo aberto"; plano de 2023 sem
  prestação mostra "sem prestação registrada"** — este é o teste que trava a
  diferença entre jornalismo e calúnia.
- O botão de link externo não dispara a expansão (`stopPropagation`).

## Fora de escopo, explicitado

- **SICONV / as 85% Finalidade Definida** — 28% de casamento ambíguo, medido.
  Reavaliar quando a API de Discricionárias e Legais sair (previsão 10/2026).
- **`meta_especial` e `empenho_especial`** — metas e empenhos por plano existem
  na fonte e são material jornalístico, mas ficam para depois.
- **Backfill histórico** — a coleta refaz tudo a cada execução, então a primeira
  execução já é o backfill.

## Rollback

Flag para `off` resolve na hora, sem deploy. A tabela e o cron podem ficar: são
inertes para quem não vê a feature.
