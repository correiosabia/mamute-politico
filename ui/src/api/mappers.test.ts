import { describe, expect, it } from 'vitest';

import { mapPropositionOutToProposicao } from './mappers';
import type { PropositionOut } from './types';

function makeProposition(overrides: Partial<PropositionOut> = {}): PropositionOut {
  return {
    id: 1,
    proposition_code: 123456,
    proposition_acronym: 'PL',
    proposition_number: 2810,
    presentation_year: 2024,
    presentation_date: '2024-07-08',
    current_status: 'Aguardando Parecer',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

describe('mapPropositionOutToProposicao', () => {
  it('prefers the proposition summary for the ementa column', () => {
    const proposicao = mapPropositionOutToProposicao(
      makeProposition({
        summary: 'Ementa completa da proposição da Câmara',
        proposition_description: 'Projeto de Lei',
      }),
    );

    expect(proposicao.ementa).toBe('Ementa completa da proposição da Câmara');
  });

  it('falls back to proposition_description when summary is missing', () => {
    const proposicao = mapPropositionOutToProposicao(
      makeProposition({
        proposition_description: 'Texto disponível sem summary',
      }),
    );

    expect(proposicao.ementa).toBe('Texto disponível sem summary');
  });

  it('maps Camara proposition keywords to tema', () => {
    const proposicao = mapPropositionOutToProposicao(
      makeProposition({
        details: {
          keywords:
            'Alteração, Lei de Benefícios da Previdência Social (1991), pensão por morte.',
        },
      }),
    );

    expect(proposicao.tema).toBe(
      'Alteração, Lei de Benefícios da Previdência Social (1991), pensão por morte',
    );
  });
});
