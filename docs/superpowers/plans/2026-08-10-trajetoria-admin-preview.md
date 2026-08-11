# Aba Trajetória (prévia admins) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aba "Trajetória" no ParlamentarDashboard com timeline eleitoral + gráfico de evolução patrimonial, renderizada apenas para admins (`useIsAdmin`).

**Architecture:** Só frontend. Novo componente `TrajetoriaTab` (recharts + tabela) consumindo o endpoint já em produção `/parliamentarians/{id}/electoral-history`; gate por renderização condicional da aba no dashboard. Spec: `docs/superpowers/specs/2026-08-10-trajetoria-admin-preview-design.md`.

**Tech Stack:** React + TypeScript, TanStack Query, recharts (já instalado), shadcn Tabs/Table, vitest + testing-library.

## Global Constraints

- Zero impacto para usuário comum: aba não renderiza e query não dispara sem admin.
- Nenhuma mudança de API, banco ou coleta.
- Dinheiro chega como string; `Number()` só na formatação (padrão EmendasTable).
- Link externo só via `getSafeExternalUrl` (padrão emendas).
- Liberação futura = remover a condição `isAdmin` em 1 lugar.

---

### Task 1: API client + componente `TrajetoriaTab` (TDD)

**Files:**
- Modify: `ui/src/api/endpoints.ts` (final do arquivo)
- Create: `ui/src/components/dashboard/TrajetoriaTab.tsx`
- Test: `ui/src/components/dashboard/TrajetoriaTab.test.tsx`

**Interfaces:**
- Produces: `ElectoralHistoryEntryOut` e `getElectoralHistory(parliamentarianId: number): Promise<{ entries: ElectoralHistoryEntryOut[] }>`; componente `<TrajetoriaTab parliamentarianId={number} />`.

- [ ] **Step 1: Teste que falha** — `TrajetoriaTab.test.tsx`:

```tsx
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TrajetoriaTab } from './TrajetoriaTab';
import * as endpoints from '@/api/endpoints';

vi.mock('@/api/endpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof endpoints>()),
  getElectoralHistory: vi.fn(),
}));

const mocked = vi.mocked(endpoints.getElectoralHistory);

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TrajetoriaTab parliamentarianId={1} />
    </QueryClientProvider>
  );
}

const ENTRIES = [
  {
    year: 2026, office: 'Governador', state: 'PR', locality: 'PARANÁ',
    party: 'PL', ballot_name: 'SERGIO MORO', result: 'Concorrendo',
    declared_assets: '1036642.25', assets_count: 12,
    source_link: 'https://divulgacandcontas.tse.jus.br/divulga/#/candidato/2026/x/PR/1',
  },
  {
    year: 2022, office: 'Senador', state: 'PR', locality: 'PARANÁ',
    party: 'UNIÃO', ballot_name: 'SERGIO MORO', result: 'Eleito',
    declared_assets: '1589369.94', assets_count: 13,
    source_link: 'https://divulgacandcontas.tse.jus.br/divulga/#/candidato/2022/x/PR/2',
  },
];

describe('TrajetoriaTab', () => {
  it('renderiza selo de prévia, disputas e patrimônio em BRL', async () => {
    mocked.mockResolvedValue({ entries: ENTRIES });
    renderTab();
    expect(await screen.findByText(/Prévia/)).toBeInTheDocument();
    expect(screen.getByText('Governador')).toBeInTheDocument();
    expect(screen.getByText('Eleito')).toBeInTheDocument();
    // BRL usa espaço não separável entre R$ e o número.
    expect(screen.getByText(/R\$\s?1\.036\.642,25/)).toBeInTheDocument();
    expect(screen.getByText(/R\$\s?1\.589\.369,94/)).toBeInTheDocument();
  });

  it('links para o TSE saem do source_link', async () => {
    mocked.mockResolvedValue({ entries: ENTRIES });
    renderTab();
    const links = await screen.findAllByRole('link', { name: /ver no TSE/i });
    expect(links[0]).toHaveAttribute('href', ENTRIES[0].source_link);
  });

  it('estado vazio mostra mensagem de não coletado', async () => {
    mocked.mockResolvedValue({ entries: [] });
    renderTab();
    expect(
      await screen.findByText(/ainda não coletado/i)
    ).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Rodar e ver falhar** — `cd ui && npx vitest run src/components/dashboard/TrajetoriaTab.test.tsx`. Expected: FAIL (módulo inexistente).

- [ ] **Step 3: Implementar.** Em `endpoints.ts` (final):

```ts
/** Uma disputa eleitoral na linha do tempo do político (CS-54). */
export interface ElectoralHistoryEntryOut {
  year: number;
  office: string | null;
  state: string | null;
  locality: string | null;
  party: string | null;
  ballot_name: string | null;
  result: string | null;
  declared_assets: string | null;
  assets_count: number | null;
  source_link: string | null;
}

export function getElectoralHistory(
  parliamentarianId: number
): Promise<{ entries: ElectoralHistoryEntryOut[] }> {
  return request<{ entries: ElectoralHistoryEntryOut[] }>(
    `/parliamentarians/${parliamentarianId}/electoral-history`
  );
}
```

`TrajetoriaTab.tsx`:

```tsx
import { useQuery } from '@tanstack/react-query';
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { getElectoralHistory, type ElectoralHistoryEntryOut } from '@/api/endpoints';
import { getSafeExternalUrl } from '@/lib/safeExternalUrl';
import { ExternalLink, Loader2 } from 'lucide-react';

interface TrajetoriaTabProps {
  parliamentarianId: number;
}

const BRL = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });

/** Valores chegam como string para não perder centavo; só viram número aqui. */
function formatBRL(value?: string | null): string {
  if (value == null || value === '') return '—';
  const parsed = Number(value);
  return Number.isFinite(parsed) ? BRL.format(parsed) : '—';
}

function resultBadgeClass(result?: string | null): string {
  const value = (result ?? '').toLowerCase();
  if (value.startsWith('eleito') || value === '2º turno')
    return 'bg-green-100 text-green-800';
  if (value === 'concorrendo') return 'bg-amber-100 text-amber-800';
  if (value === 'suplente') return 'bg-gray-100 text-gray-700';
  return 'bg-red-50 text-red-700';
}

export function TrajetoriaTab({ parliamentarianId }: TrajetoriaTabProps) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['electoral-history', parliamentarianId],
    queryFn: () => getElectoralHistory(parliamentarianId),
  });

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }
  if (isError) {
    return (
      <p className="p-4 text-sm text-muted-foreground">
        Não foi possível carregar a trajetória eleitoral.
      </p>
    );
  }

  const entries = data?.entries ?? [];
  // Gráfico em ordem cronológica; a lista fica na ordem da API (ano desc).
  const chartData = [...entries]
    .reverse()
    .filter((entry) => entry.declared_assets != null)
    .map((entry) => ({ year: entry.year, patrimonio: Number(entry.declared_assets) }));

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto">
      <span className="inline-flex w-fit items-center rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800">
        Prévia — visível só para administradores
      </span>

      {entries.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Histórico eleitoral ainda não coletado para este parlamentar.
        </p>
      ) : (
        <>
          {chartData.length >= 2 && (
            <div className="h-56 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
                  <XAxis dataKey="year" tick={{ fontSize: 12 }} />
                  <YAxis
                    tick={{ fontSize: 12 }}
                    width={90}
                    tickFormatter={(value: number) =>
                      BRL.format(value).replace(/,00$/, '')
                    }
                  />
                  <Tooltip
                    formatter={(value: number) => [BRL.format(value), 'Patrimônio declarado']}
                    labelFormatter={(year) => `Eleição de ${year}`}
                  />
                  <Line
                    type="monotone"
                    dataKey="patrimonio"
                    stroke="#b45309"
                    strokeWidth={2}
                    dot={{ r: 4 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Ano</TableHead>
                <TableHead>Cargo</TableHead>
                <TableHead>Local</TableHead>
                <TableHead>Partido</TableHead>
                <TableHead>Resultado</TableHead>
                <TableHead className="text-right">Patrimônio declarado</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map((entry: ElectoralHistoryEntryOut) => {
                const safeUrl = entry.source_link
                  ? getSafeExternalUrl(entry.source_link)
                  : null;
                return (
                  <TableRow key={`${entry.year}-${entry.office}-${entry.state}`}>
                    <TableCell className="font-medium">{entry.year}</TableCell>
                    <TableCell>{entry.office ?? '—'}</TableCell>
                    <TableCell>{entry.locality ?? entry.state ?? '—'}</TableCell>
                    <TableCell>{entry.party ?? '—'}</TableCell>
                    <TableCell>
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${resultBadgeClass(entry.result)}`}
                      >
                        {entry.result ?? '—'}
                      </span>
                    </TableCell>
                    <TableCell className="text-right">
                      {formatBRL(entry.declared_assets)}
                    </TableCell>
                    <TableCell>
                      {safeUrl && (
                        <a
                          href={safeUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                        >
                          ver no TSE <ExternalLink className="h-3 w-3" />
                        </a>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Rodar e ver passar.** (Se `getSafeExternalUrl` tiver assinatura diferente, seguir exatamente o uso do `EmendasTable`.)
- [ ] **Step 5: Commit** — `feat(ui): componente TrajetoriaTab com timeline e evolucao patrimonial`

---

### Task 2: Gate de admin no ParlamentarDashboard (TDD)

**Files:**
- Modify: `ui/src/pages/ParlamentarDashboard.tsx`
- Test: `ui/src/pages/ParlamentarDashboard.trajetoria.test.tsx`

**Interfaces:**
- Consumes: `<TrajetoriaTab parliamentarianId={numericId} />` (Task 1), `useIsAdmin()` existente.

- [ ] **Step 1: Teste que falha** — mocka `useIsAdmin`, auth e endpoints; renderiza a página via MemoryRouter e verifica a presença/ausência do trigger "TRAJETÓRIA":

```tsx
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const isAdminState = { isAdmin: false, isLoading: false };

vi.mock('@/hooks/useIsAdmin', () => ({ useIsAdmin: () => isAdminState }));
vi.mock('@/components/auth/ghost-auth/react/useGhostAuth', () => ({
  useGhostAuth: () => 'token',
}));
vi.mock('@/api/events', () => ({ sendSectionView: vi.fn() }));
vi.mock('@/api/endpoints', () => ({
  getParliamentarian: vi.fn().mockResolvedValue({
    id: 1, name: 'Sergio Moro', full_name: 'Sergio Fernando Moro',
    party: 'PL', state_elected: 'PR', type: 'Senador',
  }),
  getElectoralHistory: vi.fn().mockResolvedValue({ entries: [] }),
  listAmendments: vi.fn().mockResolvedValue([]),
}));

import ParlamentarDashboard from './ParlamentarDashboard';

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/parlamentar/1']}>
        <Routes>
          <Route path="/parlamentar/:id" element={<ParlamentarDashboard />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('gate da aba Trajetória', () => {
  beforeEach(() => {
    isAdminState.isAdmin = false;
  });

  it('não-admin não vê a aba', async () => {
    renderPage();
    await screen.findAllByText(/VOTAÇÕES/i);
    expect(screen.queryByText(/TRAJETÓRIA/i)).not.toBeInTheDocument();
  });

  it('admin vê a aba', async () => {
    isAdminState.isAdmin = true;
    renderPage();
    expect(await screen.findByText(/TRAJETÓRIA/i)).toBeInTheDocument();
  });
});
```

Nota de execução: o `vi.mock('@/api/endpoints')` acima é parcial de propósito — se o dashboard consumir outras funções do módulo (favoritos, stats, resumo de emendas), acrescentar stubs `vi.fn().mockResolvedValue(...)` para cada uma até a página renderizar; o mock deve espelhar o módulo real com `importOriginal` se a lista crescer demais.

- [ ] **Step 2: Rodar e ver falhar** (aba nunca aparece).
- [ ] **Step 3: Implementar** em `ParlamentarDashboard.tsx`:

```tsx
import { TrajetoriaTab } from '@/components/dashboard/TrajetoriaTab';
import { useIsAdmin } from '@/hooks/useIsAdmin';
// dentro do componente:
const { isAdmin } = useIsAdmin();
```

No `TabsList`, após o trigger de EMENDAS (a condição `isAdmin` é o feature
flag — remover para liberar a todos):

```tsx
{isAdmin && (
  <TabsTrigger value="trajetoria" className={parlamentarSectionTabTriggerClass}>
    TRAJETÓRIA
  </TabsTrigger>
)}
```

Após o `TabsContent` de emendas:

```tsx
{isAdmin && (
  <TabsContent value="trajetoria" className="mt-0 p-6 pt-4 h-[500px]">
    <TrajetoriaTab parliamentarianId={numericId} />
  </TabsContent>
)}
```

- [ ] **Step 4: Rodar e ver passar.**
- [ ] **Step 5: Commit** — `feat(ui): aba Trajetoria no dashboard, previa restrita a admins`

---

### Task 3: Suíte completa + build + PR

- [ ] **Step 1:** `cd ui && npx vitest run` → tudo verde; `npm run build` → sem erro de tipo.
- [ ] **Step 2:** Push + PR contra main (resumo: gate/flag, zero impacto no comum, como liberar depois).

## Self-review

- Spec coberto: client+componente (T1), gate (T2), testes de não-admin/admin/vazio/BRL/link (T1+T2), build (T3). Sem mudança de API/banco — correto.
- Sem placeholders; nomes consistentes (`getElectoralHistory`, `TrajetoriaTab`, `isAdmin`).
- Nota honesta no T2 sobre o mock parcial do endpoints — instrução de como completar, não um TBD.
