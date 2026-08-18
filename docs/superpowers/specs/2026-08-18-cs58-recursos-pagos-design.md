# CS-58 — Recursos pagos: cadeado com prévia desfocada — Design

Aprovado pelo Luiz em 2026-08-18.

## Objetivo

Emendas e Trajetória são o que diferencia o Mamute e hoje estão abertos a
qualquer usuário. A CS-58 os torna pagos **sem escondê-los**: quem não tem o
plano vê a entrada em cinza com cadeado e, ao clicar, uma prévia desfocada com
chamada para assinar. O que é pago e em qual plano libera é configuração de
painel, não código. E o gate vale no backend: desfoque no front é vitrine, não
segurança.

Isto é a segunda metade do desenho iniciado na PR #169 (feature flags), que
deixou o ponto de extensão anotado em `enabled_flags_for_tier`.

## Decisões tomadas com o Luiz (2026-08-18)

1. **O modo é por plano, não por recurso.** Vive em `feature_flag_tier`, não
   numa coluna global de `feature_flag`. Um mesmo recurso pode estar liberado
   no plano avançado, com cadeado no básico e oculto num terceiro.
2. **A prévia usa dados reais, degradados no servidor.** Os dados são públicos
   (emendas, TSE); o risco não é sigilo, é entregar o dataset completo de
   graça. O corte acontece no backend — nada fictício.
3. **O resumo de emendas acompanha a aba.** O gate é do RECURSO emendas, não
   da aba: `/amendments/summary` (card Estatísticas do perfil) entra no mesmo
   gate.
4. **Admin pode simular o estado bloqueado.** Admin sempre vê tudo, mas ganha
   um preview "ver como bloqueada" por feature, para conferir o cadeado+blur
   de ponta a ponta ANTES de liberar — inclusive com a flag ainda em
   `admins`, que é o estágio em que Emendas e Trajetória estão hoje.

## Semântica: plano × recurso vira tri-valorado

`feature_flag_tier` ganha a coluna `mode`:

| Estado no plano             | O usuário do plano vê                          |
|-----------------------------|------------------------------------------------|
| sem linha                   | nada — recurso some da tela (comportamento atual) |
| linha, `mode = 'liberado'`  | acesso pleno                                   |
| linha, `mode = 'cadeado'`   | entrada cinza + cadeado; clique = prévia desfocada + CTA |

O tri-estado de `feature_flag` (`off`/`admins`/`all`) segue intocado como
ciclo de vida do lançamento. **Cadeado só existe em `all`**: em `admins`,
não-admin continua sem ver nada — recurso não lançado não vira vitrine.
Admin resolve pleno para tudo que não está `off` (papel de admin é prévia e
conferência, não assinatura).

Sem plano/anônimo permanece como hoje: tudo oculto, falha fechado. A
interface já exige plano básico; caso raro não ganha mecanismo.

## Arquitetura

### 1. Banco

Migration alembic: coluna `mode` em `feature_flag_tier`, `text NOT NULL
DEFAULT 'liberado'`, check `mode IN ('liberado', 'cadeado')`. Linhas
existentes herdam `liberado` — ninguém perde acesso no deploy. Modelo
espelhado em `mamute_scrappers/db/models/feature_flag.py`, como o restante.

### 2. Backend — resolução

`services/feature_flags.py`:

- `enabled_flags_for_tier(db, tier_id)` passa a devolver `dict[str, str]`
  (chave → modo) em vez de `set` — exatamente a evolução anotada no
  docstring do ponto de extensão.
- `resolve_for(db, is_admin, liberadas)` devolve `dict[str, str]` com os
  valores resolvidos `'liberada' | 'bloqueada' | 'oculta'`:
  - admin → `'liberada'` para tudo que não está `off`;
  - `all` + `mode='liberado'` → `'liberada'`;
  - `all` + `mode='cadeado'` → `'bloqueada'`;
  - resto (`off`, `admins` p/ não-admin, sem linha) → `'oculta'`.
- `set_tier_flags(db, tier_id, ...)` passa a receber `{key: mode}` e a tela
  de Planos salva a lista inteira de uma vez, como hoje.

`GET /settings/feature-flags` devolve `dict[str, str]` com esses valores.
Quem não é admin continua sem saber que existe flag em modo `admins` — a
chave simplesmente vem `'oculta'`.

### 3. Backend — gate nas rotas de dado (a parte que é segurança)

Dependency nova `feature_access(key: str)` (em `api/security.py` ou módulo
próprio), usada pelas rotas de dado. Resolve o chamador pelo mesmo caminho do
`/settings/feature-flags` (Authorization opcional → admin? → tier → modo) e
injeta um objeto com `full: bool`:

- resolvido `'liberada'` (ou admin) → `full=True`, rota devolve tudo;
- `'bloqueada'` → `full=False`, rota devolve **prévia truncada**;
- `'oculta'` → **403** direto.

Prévia truncada (`full=False`) nas rotas de listagem:

- corte fixo no servidor: primeiras N linhas (N=3) em ordem determinística;
- **ignora qualquer filtro/paginação do cliente** — honrar filtro em prévia
  vira oráculo de extração (enumerar o dataset variando o filtro);
- mesmo shape de resposta (o front sabe que está bloqueado pela rota de
  flags, não precisa de marcador no payload).

Rotas e chaves:

| Rota | Chave | `full=False` |
|------|-------|--------------|
| `GET /amendments/` | `emendas` | 3 primeiras linhas, sem filtros |
| `GET /amendments/{code}/action-plans` | `emendas` | 3 primeiras linhas |
| `GET /amendments/summary` | `emendas` | **403** — o agregado é o produto; o front nem chama |
| `GET /electoral-history/parliamentarian/{id}` | `trajetoria` | 3 primeiras entradas da timeline |
| `GET /electoral-history/candidacy/{id}` | `trajetoria` | 3 primeiras entradas |

Chave nova `emendas` no registro do front (`emendas_prestacao` já existe e é
outro recurso — a prestação de contas DENTRO da aba). A aba EMENDAS, que hoje
não tem flag, passa a ter.

Custo por request: a dependency faz a mesma resolução que a rota de settings
(decode JWT + 2 queries leves). Aceitável para as 5 rotas gatadas; se pesar,
cache é otimização futura, não requisito.

### 4. Frontend

- `useFeatureFlag(key): boolean` mantém a assinatura (`=== 'liberada'`) —
  **nenhum call site atual muda**.
- Novo `useFeatureAccess(key): 'liberada' | 'bloqueada' | 'oculta'` (mesma
  query compartilhada), só para os pontos de montagem que sabem renderizar o
  estado bloqueado. Carregando/erro resolve `'oculta'` — o mais restritivo,
  como hoje.
- **Abas do perfil** (`ParlamentarDashboard`): a lista `abas` ganha o acesso
  por aba (`emendas`, `trajetoria`). `'oculta'` → aba some (como hoje);
  `'bloqueada'` → aba na lista, cinza com ícone de cadeado (lucide `Lock`),
  clicável; o conteúdo monta o componente real (que recebe a prévia truncada
  do backend) dentro de um contêiner com blur CSS + gradiente + card de CTA
  "Assine para ver tudo" apontando para `PLANS_URL`
  (`/#/portal/account/plans`, já existente em `components/auth/config.ts`).
- **Card Estatísticas**: com `emendas` bloqueada, a linha de emendas mostra
  cadeado no lugar do número e o front **não chama** `/amendments/summary`.
- **Tela de Planos** (`TierFeaturesFields`): o checkbox por recurso vira
  seletor de 3 posições — Oculto / Cadeado / Liberado. É onde o admin "marca
  recurso como pago e escolhe em quais planos libera", sem deploy.
- Painel `/admin/configuracoes` (`FeatureFlagsPanel`): o contador "liberada
  em N de M planos" passa a contar liberado+cadeado como "planos com o
  recurso" e pode denunciar os dois números.

### 5. Preview de admin — "ver como bloqueada"

Admin nunca perde acesso, mas precisa conferir a vitrine antes de vendê-la.
Cada flag no `FeatureFlagsPanel` ganha um toggle **"ver como bloqueada"**,
por admin e por navegador (estado client-side, ex.: `localStorage` — não é
config do produto, é lente de inspeção; não vai ao banco):

- com o toggle ligado, `useFeatureAccess(key)` devolve `'bloqueada'` para
  aquele admin → a UI renderiza cadeado + blur + CTA de verdade;
- as chamadas de dado saem com o header `X-Feature-Preview: <keys>`
  (interceptor único no client HTTP); a dependency `feature_access` honra o
  header **somente se o chamador é admin**, resolvendo `full=False` → a
  prévia truncada real do backend também entra na simulação;
- para não-admin o header é ignorado — usuário comum nunca vê diferença;
- funciona em qualquer estado da flag, inclusive `admins`: a simulação não
  altera estado nem plano nenhum, é só a resolução daquele request.

## Testes

Backend (`api/tests/test_feature_flags.py` + teste novo de gate):

- resolução: matriz estado × modo × admin devolve os três valores certos;
- `set_tier_flags` grava/substitui modos;
- gate: `'liberada'` devolve tudo; `'bloqueada'` trunca em N e **ignora
  filtros** (teste passa filtro e prova que a resposta não muda);
  `'oculta'` → 403; summary bloqueado → 403; admin sempre pleno;
- preview de admin: header `X-Feature-Preview` com admin → truncado; mesmo
  header sem admin → ignorado (resposta idêntica à sem header).

Front:

- `useFeatureAccess` (os três valores + fallback `'oculta'`);
- aba bloqueada renderiza cadeado e o contêiner de blur + CTA;
- aba oculta some (regressão do comportamento atual);
- `TierFeaturesFields` com seletor de 3 posições salvando `{key: mode}`;
- card Estatísticas com cadeado e sem chamada ao summary;
- toggle "ver como bloqueada" muda `useFeatureAccess` para `'bloqueada'` e
  anexa o header nas chamadas.

Gotcha do type-check: usar `npx tsc -p tsconfig.app.json --noEmit` (o
`tsconfig.json` raiz não checa nada); a main tem ~17 erros pré-existentes de
mocks — comparar contagem, não esperar zero.

## Resultado esperado (critérios do ticket)

- [ ] Admin marca/desmarca recurso como pago e escolhe em quais planos
      libera, sem deploy → seletor de 3 posições na tela de Planos.
- [ ] Usuário sem plano que libera vê entrada cinza com cadeado e, ao clicar,
      conteúdo desfocado com CTA → modo `cadeado` + prévia truncada + blur.
- [ ] Usuário com plano que libera vê o conteúdo normal → modo `liberado`.
- [ ] Rota da API recusa o dado completo sem plano, independente do front →
      dependency `feature_access` nas 5 rotas.
- [ ] Admin segue com acesso irrestrito → admin resolve `'liberada'` para
      tudo que não está `off`.
- [ ] Admin simula o estado bloqueado de qualquer feature (mesmo em
      `admins`), de ponta a ponta, sem afetar usuário nenhum → toggle "ver
      como bloqueada" + header honrado só para admin.

## Impacto e reversibilidade

- Migration só adiciona coluna com default — deploy não muda comportamento
  até o admin marcar algum plano como `cadeado`.
- O contrato de `/settings/feature-flags` muda de `bool` para `str`; front e
  back sobem juntos no mesmo deploy (monorepo, mesmo pipeline — como na #169).
- Remoção de flag continua mecânica (apagar do registro → `tsc` quebra call
  sites → desembrulhar), agora incluindo os call sites de `useFeatureAccess`
  e as dependencies `feature_access(key)` no backend, que o teste de gate
  denuncia.
