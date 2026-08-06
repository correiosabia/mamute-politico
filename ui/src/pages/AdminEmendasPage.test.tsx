import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import AdminEmendasPage from './AdminEmendasPage';
import * as adminApi from '@/api/admin';

// O AdminShell depende do LoginModalProvider; mesmo mock de AdminSettingsPage.
vi.mock('@/components/layout/AdminShell', () => ({
  AdminShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AdminEmendasPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('AdminEmendasPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('lista os autores nao casados com contagem e valor', async () => {
    vi.spyOn(adminApi, 'listUnmatchedAmendmentAuthors').mockResolvedValue([
      {
        author_name_raw: 'FATIMA PELAES',
        amendment_count: 3,
        committed_total: '3000.00',
        match_status: 'unmatched',
      },
    ]);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('FATIMA PELAES')).toBeInTheDocument();
    });
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText(/Sem correspond/i)).toBeInTheDocument();
  });

  it('traduz o motivo ambiguous para homonimo', async () => {
    vi.spyOn(adminApi, 'listUnmatchedAmendmentAuthors').mockResolvedValue([
      {
        author_name_raw: 'JOAO SILVA',
        amendment_count: 1,
        committed_total: '500.00',
        match_status: 'ambiguous',
      },
    ]);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/homônimo/i)).toBeInTheDocument();
    });
  });

  it('mostra estado vazio quando tudo casou', async () => {
    vi.spyOn(adminApi, 'listUnmatchedAmendmentAuthors').mockResolvedValue([]);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/todas as emendas casaram/i)).toBeInTheDocument();
    });
  });

  it('mostra falha quando a consulta quebra', async () => {
    vi.spyOn(adminApi, 'listUnmatchedAmendmentAuthors').mockRejectedValue(
      new Error('boom')
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/falha ao carregar/i)).toBeInTheDocument();
    });
  });
});
