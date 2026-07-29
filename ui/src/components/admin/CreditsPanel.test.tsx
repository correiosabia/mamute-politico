import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { CreditsMetrics } from '@/api/admin';
import { CreditsPanel } from './CreditsPanel';

function dados(over: Partial<CreditsMetrics> = {}): CreditsMetrics {
  return {
    disponivel: true,
    status: 'ok',
    total_credits_usd: 22,
    total_usage_usd: 10,
    disponivel_usd: 12,
    chatbot_usd: 4,
    embeddings_usd: 6,
    limiar_atencao_usd: 10,
    limiar_critico_usd: 5,
    ...over,
  };
}

describe('CreditsPanel', () => {
  it('mostra saldo e a separação chatbot x embeddings', () => {
    render(<CreditsPanel data={dados()} />);

    expect(screen.getByText('US$ 12,00')).toBeInTheDocument();
    expect(screen.getByText('US$ 4,00')).toBeInTheDocument();
    expect(screen.getByText('US$ 6,00')).toBeInTheDocument();
  });

  it('sinaliza saldo saudável sem alarme', () => {
    render(<CreditsPanel data={dados()} />);

    expect(screen.getByText(/saldo saudável/i)).toBeInTheDocument();
    expect(screen.queryByText(/reponha o saldo agora/i)).toBeNull();
  });

  it('avisa quando o saldo está baixo', () => {
    render(<CreditsPanel data={dados({ status: 'atencao', disponivel_usd: 8 })} />);

    expect(screen.getByText(/saldo baixo/i)).toBeInTheDocument();
  });

  it('no crítico, explica a consequência e oferece o caminho', () => {
    render(<CreditsPanel data={dados({ status: 'critico', disponivel_usd: 3 })} />);

    expect(screen.getByText(/saldo crítico/i)).toBeInTheDocument();
    expect(screen.getByText(/chat para de responder/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /repor no openrouter/i })).toHaveAttribute(
      'href',
      'https://openrouter.ai/settings/credits'
    );
  });

  it('provedor fora do ar não vira alarme falso', () => {
    render(
      <CreditsPanel
        data={dados({
          disponivel: false,
          status: 'desconhecido',
          total_credits_usd: null,
          disponivel_usd: null,
          chatbot_usd: null,
          embeddings_usd: null,
        })}
      />
    );

    expect(screen.getByText(/não foi possível consultar o saldo/i)).toBeInTheDocument();
    // Não pode sugerir que o chat caiu só porque a consulta de saldo falhou.
    expect(screen.getByText(/não afeta o funcionamento do chat/i)).toBeInTheDocument();
  });

  it('deixa explícito que embeddings é valor derivado', () => {
    render(<CreditsPanel data={dados()} />);

    expect(screen.getByText(/derivado/i)).toBeInTheDocument();
  });
});
