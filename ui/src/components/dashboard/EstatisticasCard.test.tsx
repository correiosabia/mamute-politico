import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { EstatisticasCard } from './EstatisticasCard';

const STATS = {
  propositions_this_week: 120,
  attendance_avg_percent: 91,
  recent_votes_count: 340,
  speeches_count: 88,
};

const RESUMO = {
  year: 2026,
  count: 12,
  committed_total: '12500000.00',
  paid_total: '3100000.00',
};

describe('EstatisticasCard', () => {
  it('mantem os quatro indicadores existentes', () => {
    render(<EstatisticasCard stats={STATS} />);
    expect(screen.getByText('120')).toBeInTheDocument();
    expect(screen.getByText('91%')).toBeInTheDocument();
    expect(screen.getByText('340')).toBeInTheDocument();
    expect(screen.getByText('88')).toBeInTheDocument();
  });

  it('mostra o bloco de emendas quando ha resumo', () => {
    render(
      <EstatisticasCard stats={STATS} amendmentsYear={2026} amendmentsSummary={RESUMO} />
    );
    expect(screen.getByText(/emendas 2026/i)).toBeInTheDocument();
    expect(screen.getByText(/destinado/i)).toBeInTheDocument();
    expect(screen.getByText(/pago/i)).toBeInTheDocument();
  });

  it('omite o bloco de emendas quando nao ha resumo', () => {
    render(<EstatisticasCard stats={STATS} />);
    expect(screen.queryByText(/emendas/i)).not.toBeInTheDocument();
  });

  it('mostra o bloco com zero quando o parlamentar nao tem emenda', () => {
    // Zero explicito e informacao; ausencia de bloco seria ambigua.
    render(
      <EstatisticasCard
        stats={STATS}
        amendmentsYear={2026}
        amendmentsSummary={{
          year: 2026,
          count: 0,
          committed_total: '0.00',
          paid_total: '0.00',
        }}
      />
    );
    expect(screen.getByText(/emendas 2026/i)).toBeInTheDocument();
  });

  it('cai para o ano do resumo quando amendmentsYear nao vem', () => {
    render(<EstatisticasCard stats={STATS} amendmentsSummary={RESUMO} />);
    expect(screen.getByText(/emendas 2026/i)).toBeInTheDocument();
  });
});
