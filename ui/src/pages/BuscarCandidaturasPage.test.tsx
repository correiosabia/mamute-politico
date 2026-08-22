import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type * as endpointsModule from '@/api/endpoints';
import type { CandidacyOut } from '@/api/types';

vi.mock('@/components/layout/Header', () => ({ Header: () => <header /> }));

const acessoState = { valor: 'liberada' as 'liberada' | 'bloqueada' | 'oculta' };
vi.mock('@/hooks/useFeatureAccess', () => ({
  useFeatureAccess: () => acessoState.valor,
}));
const toastInfo = vi.fn();
const toastSuccess = vi.fn();
vi.mock('sonner', () => ({
  toast: {
    info: (...args: unknown[]) => toastInfo(...args),
    success: (...args: unknown[]) => toastSuccess(...args),
    error: vi.fn(),
  },
}));
vi.mock('@/components/layout/CandidaturasFooter', () => ({
  CandidaturasFooter: () => <footer />,
}));

const candidatura = (over: Partial<CandidacyOut>): CandidacyOut => ({
  id: 1,
  election_year: 2026,
  tse_candidate_id: 99001,
  office_code: 5,
  office: 'Senador',
  state: 'CE',
  ballot_number: 123,
  ballot_name: 'Luciana Ferreira',
  full_name: 'LUCIANA FERREIRA DA SILVA',
  party: 'PDT',
  coalition: null,
  status: 'Aguardando julgamento',
  photo_url: null,
  parliamentarian_id: 77,
  match_status: 'matched_cpf',
  ...over,
});

const VINCULADA = candidatura({});
const SEM_VINCULO = candidatura({
  id: 2,
  tse_candidate_id: 99002,
  office_code: 6,
  office: 'Deputado Federal',
  ballot_name: 'João do Ceará',
  full_name: 'JOÃO PEREIRA LIMA',
  party: 'PT',
  parliamentarian_id: null,
  match_status: 'unmatched',
});

const listCandidacies = vi.fn();
const addMyProjectFavorite = vi.fn();

vi.mock('@/api/endpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof endpointsModule>()),
  listCandidacies: (...args: unknown[]) => listCandidacies(...args),
  addMyProjectFavorite: (...args: unknown[]) => addMyProjectFavorite(...args),
  getCandidacyFilters: vi.fn().mockResolvedValue({
    election_years: [2026],
    states: ['CE', 'SP'],
    offices: [
      { code: 5, name: 'Senador' },
      { code: 6, name: 'Deputado Federal' },
    ],
  }),
  listMyProjectFavorites: vi.fn().mockResolvedValue([]),
}));

class MockIntersectionObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

async function renderPagina() {
  const { default: BuscarCandidaturasPage } = await import('./BuscarCandidaturasPage');
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/candidaturas']}>
        <BuscarCandidaturasPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// No topo, e não dentro de um describe: os dois blocos abaixo dependem disto.
beforeEach(() => {
  vi.stubGlobal('IntersectionObserver', MockIntersectionObserver);
  listCandidacies.mockReset();
  listCandidacies.mockResolvedValue([VINCULADA, SEM_VINCULO]);
  acessoState.valor = 'liberada';
  toastInfo.mockReset();
  toastSuccess.mockReset();
  addMyProjectFavorite.mockReset();
  addMyProjectFavorite.mockResolvedValue({ id: 1, parliamentarian_id: 77 });
});

describe('BuscarCandidaturasPage', () => {

  it('lista as candidaturas com badge do cargo e partido-UF', async () => {
    await renderPagina();

    expect(await screen.findByText('Luciana Ferreira')).toBeInTheDocument();
    expect(screen.getByText('SENADO')).toBeInTheDocument();
    expect(screen.getByText('PDT - CE')).toBeInTheDocument();
    expect(screen.getByText('CÂMARA')).toBeInTheDocument();
  });

  it('busca por nome só ao submeter, e vira chip removível', async () => {
    await renderPagina();
    await screen.findByText('Luciana Ferreira');

    fireEvent.change(screen.getByLabelText('Busca por nome'), { target: { value: 'luciana' } });
    // Digitar não busca: o design tem botão PESQUISAR explícito.
    expect(listCandidacies).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: 'PESQUISAR' }));
    await waitFor(() =>
      expect(listCandidacies).toHaveBeenLastCalledWith(
        expect.objectContaining({ name: 'luciana' }),
      ),
    );

    const remover = await screen.findByRole('button', { name: 'Remover filtro luciana' });
    fireEvent.click(remover);
    await waitFor(() =>
      expect(listCandidacies).toHaveBeenLastCalledWith(
        expect.objectContaining({ name: undefined }),
      ),
    );
  });

  it('avisa e não busca quando o nome tem só um caractere', async () => {
    await renderPagina();
    await screen.findByText('Luciana Ferreira');

    fireEvent.change(screen.getByLabelText('Busca por nome'), { target: { value: 'l' } });
    fireEvent.click(screen.getByRole('button', { name: 'PESQUISAR' }));

    // O backend exige 2+ caracteres: a tela avisa em vez de gastar um 422.
    await waitFor(() =>
      expect(toastInfo).toHaveBeenCalledWith(
        'Digite pelo menos 2 caracteres para buscar por nome.',
      ),
    );
    expect(listCandidacies).not.toHaveBeenCalledWith(
      expect.objectContaining({ name: 'l' }),
    );
  });

  it('"+" monitora a candidatura vinculada a um parlamentar', async () => {
    await renderPagina();
    await screen.findByText('Luciana Ferreira');

    fireEvent.click(screen.getByRole('button', { name: 'Adicionar Luciana Ferreira aos monitorados' }));
    await waitFor(() => expect(addMyProjectFavorite).toHaveBeenCalledWith(77));
    await waitFor(() =>
      expect(toastSuccess).toHaveBeenCalledWith(
        'Luciana Ferreira adicionado(a) aos monitorados.',
      ),
    );
  });

  it('"+" fica desabilitado quando a candidatura não tem parlamentar vinculado', async () => {
    await renderPagina();
    await screen.findByText('João do Ceará');

    const botao = screen.getByRole('button', {
      name: 'Adicionar João do Ceará aos monitorados',
    });
    expect(botao).toBeDisabled();
    expect(botao).toHaveAttribute(
      'title',
      expect.stringContaining('não está vinculada a um parlamentar'),
    );
  });

  it('mostra recado próprio quando a busca não devolve nada', async () => {
    listCandidacies.mockResolvedValue([]);
    await renderPagina();

    expect(
      await screen.findByText('Nenhuma candidatura encontrada com esses filtros.'),
    ).toBeInTheDocument();
  });
});


describe('BuscarCandidaturasPage — cadeado do plano (CS-58)', () => {
  it('plano liberado vê a lista sem vitrine', async () => {
    acessoState.valor = 'liberada';
    await renderPagina();

    expect(await screen.findByText('Luciana Ferreira')).toBeInTheDocument();
    expect(screen.queryByText(/exclusivo para assinantes/i)).not.toBeInTheDocument();
  });

  it('plano em cadeado vê a chamada para assinar por cima dos resultados', async () => {
    acessoState.valor = 'bloqueada';
    await renderPagina();

    expect(await screen.findByText(/exclusivo para assinantes/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /ASSINAR PARA VER TUDO/i })).toBeInTheDocument();
  });

  it('feature não lançada ("oculta") abre a tela cheia: o link tem de funcionar', async () => {
    // Decisão do Luiz: a flag governa o BUSCAR no header, não a rota — link
    // colado abre a tela para revisão antes do lançamento.
    acessoState.valor = 'oculta';
    await renderPagina();

    expect(await screen.findByText('Luciana Ferreira')).toBeInTheDocument();
    expect(screen.queryByText(/exclusivo para assinantes/i)).not.toBeInTheDocument();
  });
});
