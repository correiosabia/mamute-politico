import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement } from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { EmendasTable } from './EmendasTable';
import * as endpoints from '@/api/endpoints';

const flagState = { emendas_prestacao: false };
vi.mock('@/hooks/useFeatureFlag', () => ({
  useFeatureFlag: (key: string) =>
    (flagState as Record<string, boolean>)[key] === true,
}));

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

/** Emenda real capturada da API do Portal em 2026-08-06. */
const EMENDA = {
  id: 1,
  amendment_code: '202632980010',
  year: 2026,
  amendment_number: '0010',
  amendment_type: 'Emenda Individual - Transferências com Finalidade Definida',
  author_name_raw: 'HEITOR SCHUCH',
  parliamentarian_id: 1,
  match_status: 'matched',
  spending_locality: 'RIO GRANDE DO SUL (UF)',
  function: 'Assistência social',
  subfunction: 'Alimentação e nutrição',
  committed_value: '2000000.00',
  settled_value: '1099734.20',
  paid_value: '500000.00',
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-01T00:00:00Z',
  planos_total: 0,
  planos_com_prestacao: 0,
  valor_executado_total: '0.00',
};

/**
 * Intl.NumberFormat pt-BR separa "R$" do número com espaço não separável
 * (U+00A0). O normalizador do Testing Library troca isso por espaço comum no
 * texto do elemento, então a busca precisa comparar já normalizado — comparar
 * com a string crua do Intl falha por um caractere invisível.
 */
const brl = (n: number) =>
  new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })
    .format(n)
    .replace(/\u00a0/g, ' ');

const byMoney = (n: number) => (content: string) =>
  content.replace(/\u00a0/g, ' ') === brl(n);

describe('EmendasTable', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    flagState.emendas_prestacao = false;
  });

  it('mostra a emenda com valores formatados em real', async () => {
    vi.spyOn(endpoints, 'listAmendments').mockResolvedValue([EMENDA]);

    renderWithClient(<EmendasTable parliamentarianId={1} year={2026} />);

    await waitFor(() => {
      expect(screen.getByText('RIO GRANDE DO SUL (UF)')).toBeInTheDocument();
    });
    expect(screen.getByText('Assistência social')).toBeInTheDocument();
    expect(screen.getByText(byMoney(2000000))).toBeInTheDocument();
    expect(screen.getByText(byMoney(500000))).toBeInTheDocument();
  });

  it('repassa parlamentar e ano para a consulta', async () => {
    const spy = vi.spyOn(endpoints, 'listAmendments').mockResolvedValue([EMENDA]);

    renderWithClient(<EmendasTable parliamentarianId={42} year={2025} />);

    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(spy).toHaveBeenCalledWith(
      expect.objectContaining({ parliamentarian_id: 42, year: 2025 })
    );
  });

  it('mostra estado vazio quando nao ha emendas', async () => {
    vi.spyOn(endpoints, 'listAmendments').mockResolvedValue([]);

    renderWithClient(<EmendasTable parliamentarianId={1} year={2026} />);

    await waitFor(() => {
      expect(screen.getByText(/nenhuma emenda encontrada/i)).toBeInTheDocument();
    });
  });

  it('mostra mensagem de falha quando a consulta quebra', async () => {
    vi.spyOn(endpoints, 'listAmendments').mockRejectedValue(new Error('boom'));

    renderWithClient(<EmendasTable parliamentarianId={1} year={2026} />);

    await waitFor(() => {
      expect(screen.getByText(/falha ao carregar/i)).toBeInTheDocument();
    });
  });

  it('trata valor nulo sem quebrar', async () => {
    vi.spyOn(endpoints, 'listAmendments').mockResolvedValue([
      { ...EMENDA, paid_value: null, spending_locality: null },
    ]);

    renderWithClient(<EmendasTable parliamentarianId={1} year={2026} />);

    await waitFor(() => {
      expect(screen.getByText('Assistência social')).toBeInTheDocument();
    });
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
  });

  it('cada linha aponta para a emenda no Portal da Transparencia', async () => {
    vi.spyOn(endpoints, 'listAmendments').mockResolvedValue([EMENDA]);
    const abrir = vi.spyOn(window, 'open').mockImplementation(() => null);

    renderWithClient(<EmendasTable parliamentarianId={1} year={2026} />);

    await waitFor(() => {
      expect(screen.getByRole('link')).toBeInTheDocument();
    });
    screen.getByRole('link').click();

    expect(abrir).toHaveBeenCalledWith(
      'https://portaldatransparencia.gov.br/emendas/detalhe?codigoEmenda=202632980010',
      '_blank',
      'noopener,noreferrer'
    );
  });

  it('linha sem codigo valido nao vira link', async () => {
    vi.spyOn(endpoints, 'listAmendments').mockResolvedValue([
      { ...EMENDA, amendment_code: '' },
    ]);

    renderWithClient(<EmendasTable parliamentarianId={1} year={2026} />);

    await waitFor(() => {
      expect(screen.getByText('Assistência social')).toBeInTheDocument();
    });
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });
});
