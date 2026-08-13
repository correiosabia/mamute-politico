import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { EmendasTable } from './EmendasTable';
import * as endpoints from '@/api/endpoints';

const flagState = { emendas_prestacao: true };
vi.mock('@/hooks/useFeatureFlag', () => ({
  useFeatureFlag: (key: string) =>
    (flagState as Record<string, boolean>)[key] === true,
}));

const abriu: string[] = [];
vi.mock('@/lib/safeExternalUrl', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/safeExternalUrl')>()),
  openSafeExternalUrl: (url: string | null) => {
    if (url) abriu.push(url);
  },
}));

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const BASE = {
  author_name_raw: 'RODOLFO NOGUEIRA',
  parliamentarian_id: 1,
  match_status: 'matched',
  subfunction: null,
  settled_value: null,
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-01T00:00:00Z',
};

const PIX = {
  ...BASE,
  id: 1,
  amendment_code: '202444660013',
  year: 2024,
  amendment_number: '0013',
  amendment_type: 'Emenda Individual - Transferências Especiais',
  spending_locality: 'MATO GROSSO DO SUL (UF)',
  function: 'Educação',
  committed_value: '1798000.00',
  paid_value: '1798000.00',
  planos_total: 3,
  planos_com_prestacao: 2,
  valor_executado_total: '445098.88',
};

const FINALIDADE = {
  ...BASE,
  id: 2,
  amendment_code: '202444660014',
  year: 2024,
  amendment_number: '0014',
  amendment_type: 'Emenda Individual - Transferências com Finalidade Definida',
  spending_locality: 'MÚLTIPLO',
  function: 'Saúde',
  committed_value: '900000.00',
  paid_value: '0.00',
  planos_total: 0,
  planos_com_prestacao: 0,
  valor_executado_total: '0.00',
};

const PLANOS = [
  {
    id_plano_acao: 1,
    codigo_plano_acao: '0903-000001',
    amendment_code: '202444660013',
    ano: 2024,
    situacao: 'CIENTE',
    beneficiario_nome: 'MUNICIPIO DE DOURADOS',
    beneficiario_cnpj: null,
    beneficiario_uf: 'MS',
    valor_custeio: null,
    valor_investimento: '500000.00',
    prestacao_situacao: 'DISPONIBILIZADO',
    prestacao_tipo: 'Final',
    prestacao_valor_executado: '325098.88',
    prestacao_valor_pendente: null,
    prestacao_data: null,
    prestacao_origem: 'novo',
  },
  {
    id_plano_acao: 3,
    codigo_plano_acao: '0903-000003',
    amendment_code: '202444660013',
    ano: 2024,
    situacao: 'CIENTE',
    beneficiario_nome: 'MUNICIPIO DE CORUMBA',
    beneficiario_cnpj: null,
    beneficiario_uf: 'MS',
    valor_custeio: null,
    valor_investimento: '898000.00',
    prestacao_situacao: null,
    prestacao_tipo: null,
    prestacao_valor_executado: null,
    prestacao_valor_pendente: null,
    prestacao_data: null,
    prestacao_origem: null,
  },
];

describe('EmendasTable com prestação de contas ligada', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    abriu.length = 0;
    flagState.emendas_prestacao = true;
  });

  it('rotula cada emenda pelo tipo', async () => {
    vi.spyOn(endpoints, 'listAmendments').mockResolvedValue([PIX, FINALIDADE]);
    renderWithClient(<EmendasTable parliamentarianId={1} />);

    expect(await screen.findByText('Pix')).toBeInTheDocument();
    expect(screen.getByText('Finalidade definida')).toBeInTheDocument();
  });

  it('mostra quantos entes prestaram contas na emenda Pix', async () => {
    vi.spyOn(endpoints, 'listAmendments').mockResolvedValue([PIX]);
    renderWithClient(<EmendasTable parliamentarianId={1} />);
    expect(await screen.findByText('2/3')).toBeInTheDocument();
  });

  it('emenda de Finalidade Definida diz que o dado não está disponível', async () => {
    vi.spyOn(endpoints, 'listAmendments').mockResolvedValue([FINALIDADE]);
    renderWithClient(<EmendasTable parliamentarianId={1} />);
    expect(await screen.findByText(/não disponível/i)).toBeInTheDocument();
  });

  it('linha Pix expande e lista os beneficiários', async () => {
    vi.spyOn(endpoints, 'listAmendments').mockResolvedValue([PIX]);
    vi.spyOn(endpoints, 'listActionPlans').mockResolvedValue(PLANOS);
    renderWithClient(<EmendasTable parliamentarianId={1} />);

    fireEvent.click(await screen.findByText('2/3'));
    expect(
      await screen.findByText('MUNICIPIO DE DOURADOS')
    ).toBeInTheDocument();
    expect(screen.getByText('MUNICIPIO DE CORUMBA')).toBeInTheDocument();
  });

  it('ente sem prestação de ano fechado NUNCA é acusado', async () => {
    // O teste que separa jornalismo de calúnia.
    vi.spyOn(endpoints, 'listAmendments').mockResolvedValue([PIX]);
    vi.spyOn(endpoints, 'listActionPlans').mockResolvedValue(PLANOS);
    renderWithClient(<EmendasTable parliamentarianId={1} />);

    fireEvent.click(await screen.findByText('2/3'));
    expect(
      await screen.findByText(/sem prestação registrada/i)
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/não prestou|sonegou|irregular/i)
    ).not.toBeInTheDocument();
  });

  it('linha de Finalidade Definida não expande', async () => {
    vi.spyOn(endpoints, 'listAmendments').mockResolvedValue([FINALIDADE]);
    const spy = vi.spyOn(endpoints, 'listActionPlans');
    renderWithClient(<EmendasTable parliamentarianId={1} />);

    fireEvent.click(await screen.findByText('Finalidade definida'));
    await waitFor(() => expect(spy).not.toHaveBeenCalled());
  });

  it('o botão do Portal não dispara a expansão', async () => {
    vi.spyOn(endpoints, 'listAmendments').mockResolvedValue([PIX]);
    const spy = vi.spyOn(endpoints, 'listActionPlans');
    renderWithClient(<EmendasTable parliamentarianId={1} />);

    fireEvent.click(
      await screen.findByRole('button', {
        name: /Portal da Transparência/i,
      })
    );
    expect(abriu[0]).toContain('portaldatransparencia.gov.br');
    await waitFor(() => expect(spy).not.toHaveBeenCalled());
  });
});
