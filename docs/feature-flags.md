# Feature flags — as regras que regem o sistema

Referência da lógica de exibição e acesso por feature, consolidada após a
CS-58 (PR #180). O histórico de decisões está nas specs
(`docs/superpowers/specs/2026-08-12-feature-flags-design.md` e
`2026-08-18-cs58-recursos-pagos-design.md`); este documento é o retrato das
regras vigentes.

## As duas camadas

O acesso de um usuário a uma feature é sempre a combinação de **duas camadas
independentes**, editadas em telas diferentes:

**Camada 1 — Estado da flag** (`/admin/configuracoes`, tabela
`feature_flag`). É o ciclo de vida do lançamento:

| Estado | Significado |
|---|---|
| `off` (Desativado) | Ninguém vê. Nem admin. |
| `admins` (Só para admins) | Admin vê normal; usuário comum não vê **nada** — nem cadeado. Estágio de prévia interna. |
| `all` (Liberado, vale o plano) | Lançou. **Não** significa "todo mundo vê": o controle passa à camada 2. |

**Camada 2 — Modo por plano** (tela de Planos, tabela
`feature_flag_tier`). Só produz efeito com a camada 1 em `all`:

| No plano | O assinante do plano vê |
|---|---|
| sem linha (Oculto) | Nada — a feature some da tela. |
| `cadeado` | Entrada cinza com cadeado; ao clicar, prévia real truncada (3 linhas, corte no servidor) desfocada + CTA de assinatura. |
| `liberado` | Acesso pleno. |

A resolução (`resolve_for`, em `api/services/feature_flags.py`) devolve um
único valor por chave para quem chamou: `'liberada' | 'bloqueada' |
'oculta'`. O front não repete regra nenhuma — só renderiza.

## Precedência: o estado manda

Cadeado **só existe em `all`**. Com a flag em `admins`, um `cadeado`
configurado no plano não afeta o usuário: ele segue sem ver nada, porque
recurso não lançado não vira vitrine. O modo gravado **não se perde** — fica
dormente e passa a valer no instante em que a flag virar `all`. Isso permite
deixar a vitrine toda configurada por plano antecipadamente: o lançamento
vira um movimento só de select.

## Admin: fora da conta, sempre

Para admin, a camada 2 **não existe**: tudo que não está `off` resolve
`'liberada'`, independente do plano dele. O papel de admin no desenho é
prévia e conferência, não assinatura.

A única forma de um admin ver o estado bloqueado é o **olhinho** ("ver como
bloqueada", por flag, em `/admin/configuracoes`):

- lente **pessoal e por navegador**: vive no `localStorage`
  (`mp-feature-preview`), não vai ao banco, não afeta mais ninguém;
- não expira sozinho — persiste a reload e login/logout até ser desligado
  (o botão fica âmbar enquanto ativo, para denunciar a lente esquecida);
- com ele ligado, a feature renderiza bloqueada (cadeado + blur + CTA) e as
  chamadas de dado saem com o header `X-Feature-Preview`, que o backend
  honra **apenas para admin** — a truncagem das 3 linhas é a real, então a
  simulação é fiel de ponta a ponta ao que um assinante sem o recurso vê;
- funciona em qualquer estado da flag, inclusive `admins`;
- degrada só `liberada → bloqueada`: preview nunca revela o que está oculto;
- usuário comum forjando o header não ganha nada — o servidor o ignora.

## Receitas rápidas

| Quero que… | Configuração |
|---|---|
| ninguém veja (nem admin) | Estado `Desativado` |
| ninguém veja (admin ainda vê) | Estado `Liberado` + `Oculto` em todos os planos |
| só admin veja | Estado `Só para admins` |
| eu (admin) veja desfocado | Olhinho da feature ligado |
| user sem o plano veja com cadeado + prévia | Estado `Liberado` + `Cadeado` nos planos que não incluem |
| user veja normal | Estado `Liberado` + `Liberado` no plano dele |

Matriz do caso que costuma confundir — flag em `Só para admins` com
`cadeado` num plano:

| Quem | Vê |
|---|---|
| Usuário do plano | Nada (estado manda; cadeado dormente) |
| Admin, olhinho desligado | Tudo, normal |
| Admin, olhinho ligado | Cadeado + prévia desfocada |

## A fronteira de segurança é o backend

O desfoque no front é vitrine. Para **emendas** e **trajetória**, a
dependency `feature_access(key)` (`api/feature_gate.py`) vale na API:

- bloqueado → listagens devolvem prévia fixa de 3 linhas (`PREVIEW_ROWS`),
  **ignorando paginação/ordenação do cliente** (honrar filtro em prévia
  vira oráculo de extração); `GET /amendments/summary` devolve 403 (o
  agregado é o produto); bens (`assets`) nunca trafegam na prévia;
- oculto → 403;
- admin → sempre pleno (exceto sob o próprio header de preview).

As demais features flagadas (mamutômetro, tags, prestação de contas) seguem
com gate só de exibição — se alguma virar paga, precisa ganhar a sua
`feature_access(key)` nas rotas. No mamutômetro, cadeado **não** habilita
escrita: `mamutometro_habilitado` exige `'liberada'` estrito.

## Convenções que continuam valendo (PR #169)

- O registro de QUAIS flags existem mora no front
  (`ui/src/lib/featureFlags.ts`); o banco só guarda estado. Chave sem linha
  vale `off` — flag nova não exige migration.
- Um portão por ponto de montagem: `useFeatureFlag(key)` (booleano; só
  `'liberada'` vale `true`) para o caso comum, `useFeatureAccess(key)`
  (tri-valor) **apenas** onde o estado bloqueado é renderizado.
- Plano novo, vindo do sync do Ghost, nasce com tudo oculto.
- Remoção de flag é mecânica: apagar do registro → `tsc` quebra os call
  sites → desembrulhar → verde. As telas de admin iteram o registro, então
  a flag some dos controles sozinha. Com a CS-58, a remoção inclui também
  os call sites de `useFeatureAccess` e a `feature_access(key)` das rotas.
