import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { fetchWordCloudTerms, saveWordCloudTerms } from '@/api/admin';
import AdminSettingsPage from './AdminSettingsPage';

vi.mock('@/components/layout/AdminShell', () => ({
  AdminShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/api/admin', () => ({
  fetchWordCloudTerms: vi.fn(),
  saveWordCloudTerms: vi.fn(),
  // A pagina passou a montar o painel de funcionalidades.
  fetchFeatureFlagsAdmin: vi.fn().mockResolvedValue([]),
  saveFeatureFlag: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const mockedFetch = vi.mocked(fetchWordCloudTerms);
const mockedSave = vi.mocked(saveWordCloudTerms);

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AdminSettingsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function painel(nome: RegExp) {
  return screen.getByRole('region', { name: nome });
}

async function adicionar(nome: RegExp, termo: string) {
  const p = painel(nome);
  fireEvent.change(within(p).getByRole('textbox', { name: /adicionar/i }), {
    target: { value: termo },
  });
  fireEvent.click(within(p).getByRole('button', { name: /adicionar/i }));
}

describe('AdminSettingsPage — filtro da nuvem de palavras', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedFetch.mockResolvedValue({
      stopwords: ['presidente', 'senador'],
      excluded_terms: ['bloco'],
    });
    mockedSave.mockImplementation(async (t) => t);
  });

  it('mostra as duas listas separadas', async () => {
    renderPage();
    await screen.findByText('presidente');

    expect(within(painel(/stopwords/i)).getByText('presidente')).toBeInTheDocument();
    expect(within(painel(/termos irrelevantes/i)).getByText('bloco')).toBeInTheDocument();
  });

  it('explica a diferença entre os dois filtros', async () => {
    renderPage();
    await screen.findByText('presidente');

    // Usar o filtro errado quebra a nuvem; a distinção não pode ficar implícita.
    expect(screen.getByText(/de dentro de expressões/i)).toBeInTheDocument();
    expect(screen.getByText(/descartam a entrada inteira/i)).toBeInTheDocument();
  });

  it('adiciona um termo à lista certa', async () => {
    renderPage();
    await screen.findByText('presidente');

    await adicionar(/stopwords/i, 'gente');

    expect(within(painel(/stopwords/i)).getByText('gente')).toBeInTheDocument();
    expect(within(painel(/termos irrelevantes/i)).queryByText('gente')).toBeNull();
  });

  it('normaliza o termo digitado', async () => {
    renderPage();
    await screen.findByText('presidente');

    await adicionar(/stopwords/i, '  GENTE  ');

    expect(within(painel(/stopwords/i)).getByText('gente')).toBeInTheDocument();
  });

  it('não duplica termo já existente', async () => {
    renderPage();
    await screen.findByText('presidente');

    await adicionar(/stopwords/i, 'presidente');

    expect(within(painel(/stopwords/i)).getAllByText('presidente')).toHaveLength(1);
  });

  it('remove um termo', async () => {
    renderPage();
    await screen.findByText('presidente');

    const p = painel(/stopwords/i);
    fireEvent.click(within(p).getByRole('button', { name: /remover presidente/i }));

    expect(within(p).queryByText('presidente')).toBeNull();
  });

  it('só salva quando o admin manda, e envia as duas listas', async () => {
    renderPage();
    await screen.findByText('presidente');

    await adicionar(/stopwords/i, 'gente');
    expect(mockedSave).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /salvar/i }));

    await waitFor(() => expect(mockedSave).toHaveBeenCalledTimes(1));
    expect(mockedSave.mock.calls[0][0]).toEqual({
      stopwords: ['gente', 'presidente', 'senador'],
      excluded_terms: ['bloco'],
    });
  });

  it('sinaliza que há alteração não salva', async () => {
    renderPage();
    await screen.findByText('presidente');

    expect(screen.queryByText(/alterações não salvas/i)).toBeNull();

    await adicionar(/stopwords/i, 'gente');

    expect(screen.getByText(/alterações não salvas/i)).toBeInTheDocument();
  });
});
