import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { DashboardActivityPropositionOut } from '@/api/types';
import { Timeline } from './Timeline';

describe('Timeline', () => {
  it('uses monitored authors when proposition details do not expose raw authorship', () => {
    const camaraAmendment: DashboardActivityPropositionOut = {
      id: 48475,
      proposition_code: 2624861,
      title: 'EMC 1/2026',
      link: 'https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao=2624861',
      proposition_acronym: 'EMC',
      proposition_number: 1,
      presentation_year: 2026,
      agency_id: null,
      proposition_type_id: null,
      proposition_status_id: null,
      current_status: 'Apresentação do REQ n. 3131/2026',
      proposition_description: 'Emenda à PEC',
      presentation_date: '2026-05-14',
      presentation_month: 5,
      summary: null,
      details: {},
      created_at: '2026-05-14T00:00:00',
      updated_at: '2026-05-14T00:00:00',
      monitored_authors: [
        {
          id: 86,
          name: 'Adilson Barroso',
          full_name: 'ADILSON BARROSO OLIVEIRA',
          party: 'PL',
          state_elected: 'SP',
          type: 'Deputado',
        },
      ],
    };

    render(<Timeline propositions={[camaraAmendment]} votes={[]} />);

    expect(screen.getByText('Adilson Barroso PL - SP')).toBeInTheDocument();
  });
});
