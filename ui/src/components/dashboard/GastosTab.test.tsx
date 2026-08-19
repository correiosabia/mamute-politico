import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement } from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { GastosTab, pivotMonthly } from './GastosTab';
import * as endpoints from '@/api/endpoints';
import type { ExpenseOut, ExpenseSummaryOut } from '@/api/types';

// O recharts mede o container com ResizeObserver, que o jsdom não tem.
// Atribuição condicional: o setup global do vitest pode já ter definido um, e
// redefinir via stubGlobal quebra com "Cannot redefine property".
if (typeof globalThis.ResizeObserver === 'undefined') {
  class ResizeObserverMock {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  (globalThis as Record<string, unknown>).ResizeObserver = ResizeObserverMock;
}

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

/** Gasto real capturado do CSV da Câmara em 2026-08-19. */
const GASTO_CAMARA: ExpenseOut = {
  id: 1,
  house: 'camara',
  source_key: '1:7883485:0',
  parliamentarian_id: 1,
  year: 2026,
  month: 2,
  expense_type: 'MANUTENÇÃO DE ESCRITÓRIO DE APOIO À ATIVIDADE PARLAMENTAR',
  supplier_name: 'ALARES',
  supplier_id: '633.560.420/0018-0',
  document_number: '5771570',
  document_date: '2026-02-28',
  details: null,
  document_value: '104.58',
  glosa_value: '0.00',
  net_value: '104.58',
  document_url:
    'https://www.camara.leg.br/cota-parlamentar/documentos/publ/2227/2025/7883485.pdf',
  created_at: '2026-08-19T00:00:00Z',
  updated_at: '2026-08-19T00:00:00Z',
};

const SUMMARY: ExpenseSummaryOut = {
  year: 2026,
  count: 2,
  total: '304.58',
  monthly: [
    {
      month: 2,
      expense_type: 'MANUTENÇÃO DE ESCRITÓRIO DE APOIO À ATIVIDADE PARLAMENTAR',
      total: '104.58',
    },
    { month: 3, expense_type: 'TELEFONIA', total: '200.00' },
  ],
  top_suppliers: [
    {
      supplier_name: 'ALARES',
      supplier_id: '633.560.420/0018-0',
      total: '104.58',
      count: 1,
    },
  ],
};

const VAZIO: ExpenseSummaryOut = {
  year: 2026,
  count: 0,
  total: '0.00',
  monthly: [],
  top_suppliers: [],
};

describe('GastosTab', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('mostra fornecedor, tipo e link do documento', async () => {
    vi.spyOn(endpoints, 'getExpensesSummary').mockResolvedValue(SUMMARY);
    vi.spyOn(endpoints, 'listExpenses').mockResolvedValue([GASTO_CAMARA]);

    renderWithClient(<GastosTab parliamentarianId={1} />);

    await waitFor(() => {
      expect(screen.getAllByText('ALARES').length).toBeGreaterThan(0);
    });
    expect(
      screen.getByRole('button', { name: 'Ver o documento fiscal na fonte' })
    ).toBeInTheDocument();
    expect(screen.getByText(/Principais fornecedores/)).toBeInTheDocument();
  });

  it('mostra estado vazio com o ano', async () => {
    vi.spyOn(endpoints, 'getExpensesSummary').mockResolvedValue(VAZIO);
    vi.spyOn(endpoints, 'listExpenses').mockResolvedValue([]);

    renderWithClient(<GastosTab parliamentarianId={1} />);

    await waitFor(() => {
      expect(
        screen.getByText(/Nenhum gasto de cota encontrado/)
      ).toBeInTheDocument();
    });
  });

  it('mostra erro quando a API falha', async () => {
    vi.spyOn(endpoints, 'getExpensesSummary').mockRejectedValue(
      new Error('boom')
    );
    vi.spyOn(endpoints, 'listExpenses').mockResolvedValue([]);

    renderWithClient(<GastosTab parliamentarianId={1} />);

    await waitFor(() => {
      expect(
        screen.getByText('Falha ao carregar os gastos do parlamentar.')
      ).toBeInTheDocument();
    });
  });
});

describe('pivotMonthly', () => {
  it('pivota mês × tipo nas linhas do gráfico', () => {
    const { rows, series } = pivotMonthly(SUMMARY);
    expect(rows).toHaveLength(12);
    expect(series).toHaveLength(2);
    const fev = rows[1];
    const manutencao = series.find((s) => s.startsWith('MANUTENÇÃO'));
    expect(manutencao).toBeDefined();
    expect(fev[manutencao as string]).toBeCloseTo(104.58);
    expect(rows[2]['TELEFONIA']).toBeCloseTo(200);
  });

  it('colapsa tipos além dos 6 maiores em "Outras despesas"', () => {
    const monthly = Array.from({ length: 8 }, (_, i) => ({
      month: 1,
      expense_type: `TIPO ${i}`,
      // TIPO 7 é o maior, TIPO 0 o menor: os dois menores viram "Outras".
      total: String((i + 1) * 100),
    }));
    const { rows, series } = pivotMonthly({
      ...VAZIO,
      count: 8,
      monthly,
    });
    expect(series).toHaveLength(7); // 6 maiores + Outras
    expect(series).toContain('Outras despesas');
    // TIPO 0 (100) + TIPO 1 (200) somam em "Outras despesas".
    expect(rows[0]['Outras despesas']).toBeCloseTo(300);
  });
});
