# Feature flags gerenciáveis pelo admin — Design

Data: 2026-08-12 · Épico CS-11 · PR 1 de 2 (a PR 2 é a CS-56, que nasce usando este mecanismo)

## Objetivo

Mecanismo único de feature flag para o projeto, com três estados
(`off` / `admins` / `all`), ligado e desligado em `/admin/configuracoes` sem
redeploy. Toda feature nova passa a nascer atrás de uma flag.

A Trajetória, que hoje tem um gate `isAdmin` improvisado em dois pontos do
`ParlamentarDashboard.tsx`, migra para este mecanismo nesta mesma PR — ela é a
cobaia real que prova o desenho antes de qualquer feature nova depender dele.

## Decisões tomadas com o Luiz (2026-08-12)

| Decisão | Escolha |
|---|---|
| Estados | `off`, `admins`, `all` — exatamente três |
| Onde se gerencia | `/admin/configuracoes` (`AdminSettingsPage`), nunca por env var |
| O que a flag controla | **Só a UI.** A API continua aberta |
| Estratégia de saída | **Remover a flag do código.** Não existe "deixar no código e esconder o controle" |
| Quem pode alterar | Admin logado (gate existente) ou o Luiz direto no banco |
| Divisão em PRs | Duas: (1) infra + migração da Trajetória, (2) CS-56 emendas |

## A decisão central: por que remover em vez de esconder o controle

Foi considerado manter a flag no código e apenas ocultar o controle na tela,
para ninguém reverter uma feature já consolidada. **Foi descartado**, porque uma
flag que não pode ser desligada não é uma flag — é um `if` permanentemente
verdadeiro que cobra todos os custos e não entrega o benefício:

- O branch continua no código, então toda edição futura naquela região precisa
  raciocinar sobre "e se estiver off?".
- Aninhamento de flags não é evitado, é **garantido**: a flag velha nunca sai,
  então a próxima nasce dentro dela.
- Os testes ou continuam cobrindo os dois braços (desperdício) ou param de
  cobrir o braço `off` (e aí é código morto não testado).

E perde-se a única vantagem real: poder desligar de verdade num incidente.

A objeção legítima é que "lembrar de remover" não é estratégia. Por isso a
remoção não depende de disciplina: ela é **mecânica e verificada pelo
compilador** (ver "Procedimento de remoção").

## Arquitetura

O registro de **quais flags existem** mora em TypeScript. O banco guarda apenas
**em que estado cada uma está**. Essa separação é o que faz o resto funcionar.

### 1. Banco — `feature_flag`

Migration nova em `mamute_scrappers/migrations/versions/`, encadeada a partir do
head `e6f7a8b9c0d1` (o mesmo que está em produção).

```
key         text        PK
state       text        NOT NULL  -- 'off' | 'admins' | 'all'
updated_at  timestamptz NOT NULL  server_default now(), onupdate now()
```

- **Linha ausente = `off`.** É o que faz toda feature nova nascer desligada sem
  precisar de migration por flag.
- A migration inicial semeia `('trajetoria', 'admins')`, para a Trajetória não
  regredir no deploy — hoje ela já está visível para admins em produção.
- `CHECK (state IN ('off','admins','all'))`, para o banco recusar estado
  inválido mesmo se alguém editar na mão.

Modelo espelhado em `mamute_scrappers/db/models/feature_flag.py` e
`api/db/models/feature_flag.py`, como as demais tabelas do projeto.

### 2. Backend

**`api/services/feature_flags.py`** (segue o padrão de
`api/services/word_cloud_terms.py`):

- `get_states(db) -> dict[str, str]` — todas as linhas.
- `resolve_for(db, is_admin: bool) -> dict[str, bool]` — aplica a regra:
  `all` → `True`; `admins` → `is_admin`; `off` → `False`.
- `set_state(db, key, state) -> None` — upsert, com validação do estado.

**`api/security.py`** ganha `resolve_ghost_admin(request, authorization) -> str | None`,
que é a lógica atual de `require_ghost_admin` **sem levantar exceção**.
`require_ghost_admin` passa a delegar nela e a levantar o 404 como hoje. Isso é
necessário porque o endpoint público precisa saber se o chamador é admin sem
transformar "não é admin" em erro.

**Rotas:**

| Rota | Quem acessa | Devolve |
|---|---|---|
| `GET /settings/feature-flags` | usuário logado (router `settings`, já sob `auth_dependencies`) | `{"trajetoria": false, ...}` — booleano **já resolvido** para quem chamou |
| `GET /admin/settings/feature-flags` | admin | `[{key, state, updated_at}]` — tri-estado cru |
| `PUT /admin/settings/feature-flags/{key}` | admin | `{key, state, updated_at}` após gravar |

O endpoint público devolver booleano resolvido (e não o tri-estado) é
deliberado: mantém `useFeatureFlag('x')` devolvendo `boolean` puro, e call site
simples é o que torna a remoção barata.

### 3. Frontend

**`ui/src/lib/featureFlags.ts`** — o registro, fonte da verdade de quais flags
existem:

```ts
export const FEATURE_FLAGS = {
  trajetoria: { label: 'Aba Trajetória', since: '2026-08-10' },
} as const;

export type FeatureFlagKey = keyof typeof FEATURE_FLAGS;
```

`since` é literal no código (a data de nascimento da flag), então a tela mostra
a idade sem envolver o banco.

**`ui/src/hooks/useFeatureFlag.ts`**:

```ts
export function useFeatureFlag(key: FeatureFlagKey): boolean
```

Uma única `useQuery` compartilhada (`queryKey: ['feature-flags']`,
`staleTime: 5 min`, mesmo perfil do `useIsAdmin`), então N chamadas do hook não
viram N requests. Enquanto carrega, devolve `false` — feature nova aparecendo
só depois de resolver é preferível a piscar na tela de quem não deveria vê-la.

**`ui/src/pages/AdminSettingsPage.tsx`** — seção "Funcionalidades" acima da
nuvem de palavras, com um seletor de três estados por flag.

A tela **itera sobre `FEATURE_FLAGS`, não sobre a resposta do banco**. Duas
consequências que são o ponto do desenho:

- Chave no registro sem linha no banco → aparece como `off`. Funciona sem seed.
- Linha no banco sem chave no registro → **não aparece**. É assim que uma flag
  removida some do controle sozinha, sem precisar de um segundo mecanismo para
  esconder o botão.

Cada linha mostra `label`, o seletor e a idade derivada de `since`
("criada há 87 dias"), destacada em âmbar acima de 60 dias — empurrão para a
flag não envelhecer esquecida.

### 4. Migração da Trajetória

`ParlamentarDashboard.tsx` hoje checa `isAdmin` em dois lugares (linhas 241 e
262: `TabsTrigger` e `TabsContent`). Passa a checar
`useFeatureFlag('trajetoria')` em **um** lugar, derivando as abas de um array:

```ts
const abas = [
  { value: 'votacoes',     label: 'VOTAÇÕES',      content: <VotacoesTable ... /> },
  ...
  ...(trajetoriaOn ? [{ value: 'trajetoria', label: 'TRAJETÓRIA', content: <TrajetoriaTab ... /> }] : []),
];
```

O `useIsAdmin()` sai do `ParlamentarDashboard` (o hook continua existindo e em
uso no `App.tsx` e no `Header.tsx`, que são guarda de rota admin, não feature
flag — esses **não** mudam).

O selo "Prévia — visível só para administradores" dentro do `TrajetoriaTab`
continua como está: ele descreve o estado atual da flag e sai junto quando a
flag for para `all`.

## Regras de uso (vão para o docstring de `featureFlags.ts`)

1. **Uma flag, um portão, no ponto de montagem.** O custo de uma flag não é a
   flag: é em quantos lugares ela é lida. Se a feature é uma tela ou uma aba, o
   portão é onde ela é montada. Se for um enriquecimento dentro de um componente
   existente, o portão fica dentro desse componente e não vaza para o pai.

2. **Flag não aninha em flag.** Se você precisa melhorar algo que ainda está
   atrás de uma flag, você estende a feature existente — não cria uma segunda
   flag dentro dela. Como a feature ainda não saiu para ninguém, não há o que
   separar.

3. **Isto é controle de apresentação, não fronteira de segurança.** A API
   continua aberta e qualquer um a chama direto. Nunca use este mecanismo para
   esconder algo que não pode ser visto.

## Procedimento de remoção

Quando a feature está consolidada em produção:

1. Apagar a linha correspondente de `FEATURE_FLAGS`.
2. Rodar `tsc`. Ele quebra em **todos** os call sites, porque
   `useFeatureFlag('trajetoria')` deixa de tipar.
3. Desembrulhar cada condicional apontada pelo compilador.
4. `tsc` verde = terminou. Está provado que não sobrou uso.
5. A linha no banco fica órfã e inerte; some do `/admin/configuracoes`
   automaticamente, porque a tela renderiza a partir do registro.

O passo 2 é o que substitui disciplina por garantia: a remoção falha **em voz
alta** (erro de compilação), não silenciosamente.

Limpeza das linhas órfãs do banco: nenhuma ação obrigatória. Se um dia
incomodarem, um `DELETE` avulso resolve — elas não afetam nada.

## Testes

**API** (`api/tests/test_feature_flags.py`, padrão dos testes existentes com
SQLite):
- `resolve_for` com `is_admin=False`: `all` → `True`, `admins` → `False`, `off` → `False`.
- `resolve_for` com `is_admin=True`: `all` → `True`, `admins` → `True`, `off` → `False`.
- Chave sem linha no banco não aparece na resposta (o front a lê como `off`).
- `PUT` com estado inválido → 422; `PUT` sem ser admin → 404 (gate existente).
- `PUT` cria a linha quando ela não existe e atualiza quando existe.

**UI** (Vitest + testing-library):
- `useFeatureFlag` devolve `false` durante o carregamento.
- `AdminSettingsPage` lista as chaves do registro, inclusive as sem linha no
  banco (como `off`), e **não** lista linha do banco fora do registro — este é o
  teste que trava a propriedade "flag removida some do controle".
- `ParlamentarDashboard`: aba Trajetória ausente com a flag `off`, presente com
  a flag ligada. Adaptar o `ParlamentarDashboard.trajetoria.test.tsx` existente,
  que hoje mocka `useIsAdmin`, para mockar `useFeatureFlag`.

## Impacto e reversibilidade

- Usuário comum: um request a mais por sessão (`/settings/feature-flags`,
  cacheado 5 min). A Trajetória continua invisível para ele, como hoje.
- Admin: a Trajetória continua visível, porque a migration semeia `admins`.
- Rollback: reverter o deploy restaura o gate `isAdmin`. A tabela `feature_flag`
  sobra sem uso e não quebra nada.
