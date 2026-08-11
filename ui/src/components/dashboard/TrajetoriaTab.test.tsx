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
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <TrajetoriaTab parliamentarianId={1} />
    </QueryClientProvider>
  );
}

const ENTRIES = [
  {
    year: 2026,
    office: 'Governador',
    state: 'PR',
    locality: 'PARANÁ',
    party: 'PL',
    ballot_name: 'SERGIO MORO',
    result: 'Concorrendo',
    declared_assets: '1036642.25',
    assets_count: 12,
    source_link:
      'https://divulgacandcontas.tse.jus.br/divulga/#/candidato/2026/x/PR/1',
  },
  {
    year: 2022,
    office: 'Senador',
    state: 'PR',
    locality: 'PARANÁ',
    party: 'UNIÃO',
    ballot_name: 'SERGIO MORO',
    result: 'Eleito',
    declared_assets: '1589369.94',
    assets_count: 13,
    source_link:
      'https://divulgacandcontas.tse.jus.br/divulga/#/candidato/2022/x/PR/2',
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
    expect(await screen.findByText(/ainda não coletado/i)).toBeInTheDocument();
  });
});
