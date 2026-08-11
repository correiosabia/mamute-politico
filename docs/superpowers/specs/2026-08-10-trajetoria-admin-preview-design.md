# Prévia da Trajetória eleitoral na tela do político (admins) — Design

Data: 2026-08-10 · Relacionada: CS-54 (backend pronto, PRs #165/#166) · Épico CS-11

## Objetivo

Aba "Trajetória" no `ParlamentarDashboard` mostrando a timeline eleitoral e a
evolução patrimonial do parlamentar, visível **somente para usuários
administradores** (mesmo gate do painel admin), funcionando como feature flag:
prévia interna agora, liberação para todos depois com a remoção de uma
condição. Requisito inegociável: zero impacto para o usuário comum.

## Decisões tomadas com o Luiz (2026-08-10)

| Decisão | Escolha |
|---|---|
| Gate | Somente na UI, via `useIsAdmin()` (whoami já existente). Endpoint continua como está — dado é público do TSE |
| Posição | Nova aba "Trajetória" ao lado de Proposições/Votações/Taquigráficas/Emendas |
| Escopo | Só parlamentares da plataforma (a tela já é deles); nada de candidatos não-parlamentares |
| Liberação futura | Remover a condição `isAdmin` da renderização da aba (1 lugar) |

## Componentes

1. **`ui/src/api/endpoints.ts`** — tipo `ElectoralHistoryEntryOut` (`year:
   number; office, state, locality, party, ballot_name, result: string|null;
   declared_assets: string|null; assets_count: number|null; source_link:
   string|null`) e `getElectoralHistory(parliamentarianId: number)` chamando
   `GET /parliamentarians/{id}/electoral-history` (já em produção, resposta
   `{entries: [...]}` ordenada por ano desc; dinheiro como string).
2. **`ui/src/components/dashboard/TrajetoriaTab.tsx`** — componente novo:
   - Selo "Prévia — visível só para administradores" no topo.
   - Gráfico de evolução patrimonial: recharts `LineChart` (dependência já
     instalada), X = ano, Y = `declared_assets` (Number() só na exibição),
     apenas entradas com patrimônio não-nulo; tooltip e eixo em BRL
     (`Intl.NumberFormat('pt-BR')`, padrão do `EmendasTable`). Com menos de 2
     pontos com patrimônio, o gráfico é omitido (só a lista).
   - Lista de disputas (ano desc, ordem da API): ano, cargo, local
     (`locality` com fallback `state`), partido, badge de resultado
     (Eleito*/2º turno = verde, Concorrendo = âmbar, Suplente = cinza,
     demais = vermelho claro), patrimônio do ano e link "ver no TSE"
     (`source_link` via `getSafeExternalUrl`, como nas emendas).
   - Estados: loading (Loader2), erro ("Não foi possível carregar"), vazio
     ("Histórico eleitoral ainda não coletado para este parlamentar").
   - A query (`useQuery`) vive dentro do componente: quem não renderiza a
     aba não dispara request.
3. **`ui/src/pages/ParlamentarDashboard.tsx`** — `useIsAdmin()` (hook
   existente, cacheado 5 min, já usado no Header — zero request extra);
   `TabsTrigger`/`TabsContent` da "Trajetória" renderizados apenas quando
   `isAdmin === true`.

## Impacto no usuário comum

Nenhum: a aba não renderiza, a query não dispara, e o `useIsAdmin` já roda
hoje em toda sessão (Header). Nenhuma mudança de API, banco ou coleta.

## Testes

Vitest + testing-library, padrão dos testes existentes da UI:
- Não-admin: aba "Trajetória" ausente do DOM.
- Admin: aba presente; conteúdo renderiza entradas mockadas (cargo, resultado,
  patrimônio formatado em BRL).
- Estado vazio (entries=[]) mostra a mensagem de "ainda não coletado".
- `source_link` abre via mecanismo seguro de URL externa.

## Fora de escopo

- Trava do endpoint no servidor (decisão explícita: dado público, gate só de UI).
- Timeline de candidatos não-parlamentares (tela futura, CS-13).
- Correção inflacionária dos valores (exibição nominal, decisão de produto).
