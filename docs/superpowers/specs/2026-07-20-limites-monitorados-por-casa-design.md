# Limites de parlamentares monitorados por casa (CS-19)

**Data:** 2026-07-20
**Branch:** `feat/limites-monitorados-por-casa`
**Jira:** CS-19 (segmentação deputado/senador → base para ajuste de tiers por casa)

## Contexto

A segmentação deputado/senador (Câmara/Senado) **já existe** ponta a ponta no
código:

- **Dado:** `Parliamentarian.type` (`api/db/models/parliamentarian.py:17`) guarda
  deputado/senador; a casa é derivada por `_house_of()`
  (`api/services/admin_metrics.py:32`) e `casaFromType()`
  (`ui/src/api/mappers.ts:67`).
- **API:** `GET /parliamentarians/` já filtra por `?type=deputado&type=senado`
  (`api/routers/parliamentarians.py:352`).
- **UI:** o fluxo "selecionar parlamentares" já tem o seletor de casa
  (`CongressoSelector.tsx` / `ParlamentarSelector.tsx`).

O que **não** existe: **limites de tier por casa**. Hoje o limite de
parlamentares monitorados (`qtd_termos`) é um total único global
(`api/routers/projects.py:518`), somando deputados e senadores juntos.

## Objetivo

Substituir o limite total global de monitorados por **limites separados por
casa** (deputado vs senador), preservando acesso de clientes existentes no
deploy. A cota de IA permanece global (fora de escopo).

## Decisões (travadas no brainstorming)

1. **Escopo:** só o limite de **monitorados** vira por casa. IA continua global.
2. **Relação com o global:** **substituir**. O total global deixa de ser a fonte
   de verdade da validação; cada tier passa a ter limite por casa. Total efetivo
   = soma das casas.
3. **Rollout sem regressão:** migração semeia, para cada tier,
   `qtd_termos_camara = qtd_termos_senado = qtd_termos` atual. Ninguém perde
   acesso. Números finais por casa são definidos depois pelo Mauricio via painel
   admin.
4. **Representação:** novas chaves no JSONB `tiers.detalhes`
   (`qtd_termos_camara`, `qtd_termos_senado`). Sem migração de schema.

## Design

### 1. Dado / config

- Novas chaves em `tiers.detalhes`: `qtd_termos_camara`, `qtd_termos_senado`
  (inteiros ≥ 0).
- `Tiers` (`api/db/models/project.py`) ganha accessors tipados
  `qtd_termos_camara` / `qtd_termos_senado` (espelhando `qtd_termos`).
- `qtd_termos` global vira **legado**: não é mais lido na validação; pode ser
  exposto como derivado (soma) onde ainda for referenciado.
- `MAMUTE_TIER_LIMITS_JSON` passa a aceitar as chaves por casa; env mantém
  precedência sobre DB. `.env.example` atualizado.

### 2. Enforcement (backend — `api/routers/projects.py`)

- `_get_project_favorite_count`: passa a contar **por casa**, via join
  `ProjetosParliamentarian → Parliamentarian.type` + `_house_of()`. Retorna
  `{"camara": n, "senado": m}` (ou uma função que aceita a casa).
- `_project_favorite_limit`: resolve o limite **da casa** informada, na mesma
  ordem de precedência atual (env → DB tier). O override por-projeto legado
  (`Projetos.qtd_termos`) fica fora de escopo (ver abaixo).
- `POST /me/favorites`: determina a casa do parlamentar sendo adicionado
  (`_house_of(parliamentarian.type)`) e valida contra o limite **daquela casa**.
  Mensagem de erro específica: *"Limite de deputados monitorados atingido"* /
  *"Limite de senadores monitorados atingido"* (403).

### 3. Quota API + UI

- `GET /me/favorites/quota` retorna
  `{"camara": {"used": n, "limit": L}, "senado": {"used": m, "limit": L}}`.
- `ParlamentarSelector.tsx` (~168-176): usa a casa já selecionada para mostrar
  uso/limite **daquela casa** e bloquear o "add" quando ela lota. Tipos do
  cliente (`ui/src/api/*`) atualizados.

### 4. Migração (seed sem regressão)

- Script idempotente único: para cada tier sem chaves por casa, seta
  `qtd_termos_camara = qtd_termos_senado = qtd_termos` atual.
- Atualiza `MAMUTE_TIER_LIMITS_JSON` no `.env.example` para o formato por casa.

### 5. Admin

- `TierDetailsUpdate` (`api/routers/admin.py:69`) ganha `qtd_termos_camara` /
  `qtd_termos_senado`.
- `PUT /admin/tiers/{id}` persiste os campos.
- Painel admin (`ui/src/pages/AdminPage.tsx` + `ui/src/api/admin.ts`) ganha os
  dois campos de edição por casa.

### 6. Testes

- Atualiza `api/tests/test_project_favorite_limits.py` para o modelo por casa.
- Novos casos: deputado lota mas senador ainda tem vaga (e vice-versa); erro
  específico por casa; precedência env → DB por casa; migração idempotente.
- UI: teste do bloqueio por casa no seletor (se houver suíte de UI aplicável).

## Fora de escopo

- **Cota de IA por casa** — permanece global.
- **Override por-projeto `Projetos.qtd_termos`** (coluna) — fallback global raro.
  Mantido intocado; como a migração semeia todos os tiers com chaves por casa,
  na prática deixa de ser consultado. Se algum projeto tiver override custom,
  tratamos em follow-up.
- **Números finais por casa de cada tier** — decisão de produto (Mauricio, via
  painel admin). Aqui entregamos o mecanismo + seed sem regressão.

## Edge cases

- `type` ambíguo/nulo → `_house_of` cai em `camara` (comportamento atual
  preservado).
- Tier sem chaves por casa após migração (novo tier criado direto) → sem limite
  configurado; definir default seguro (0 = bloqueia, ou herda `qtd_termos`).
  Decisão de implementação: herdar `qtd_termos` como fallback de leitura para não
  bloquear inadvertidamente.
