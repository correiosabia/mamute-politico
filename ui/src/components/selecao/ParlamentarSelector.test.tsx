import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { listParliamentarians } from '@/api/endpoints';
import type { ParliamentarianOut } from '@/api/types';
import { ParlamentarSelector } from './ParlamentarSelector';

vi.mock('@/api/endpoints', () => ({
  listParliamentarians: vi.fn(),
}));

class MockIntersectionObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

const mockListParliamentarians = vi.mocked(listParliamentarians);

const parliamentarian: ParliamentarianOut = {
  id: 42,
  type: 'deputado',
  parliamentarian_code: 4242,
  name: 'Alan Rick',
  full_name: 'Alan Rick Miranda',
  email: null,
  telephone: null,
  cpf: null,
  status: 'Exercício',
  party: 'UNIÃO',
  state_of_birth: null,
  city_of_birth: null,
  state_elected: 'AC',
  site: null,
  education: null,
  office_name: null,
  office_building: null,
  office_number: null,
  office_floor: null,
  office_email: null,
  biography_link: null,
  biography_text: null,
  details: null,
  photo_url: '',
  created_at: '2026-06-25T00:00:00Z',
  updated_at: '2026-06-25T00:00:00Z',
};

function renderSelector(onAddParlamentar = vi.fn()) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ParlamentarSelector
          casaSelecionada="camara"
          parlamentaresSelecionados={[]}
          onAddParlamentar={onAddParlamentar}
          onRemoveParlamentar={vi.fn()}
        />
      </MemoryRouter>
    </QueryClientProvider>
  );

  return { onAddParlamentar };
}

describe('ParlamentarSelector', () => {
  beforeEach(() => {
    vi.stubGlobal('IntersectionObserver', MockIntersectionObserver);
    mockListParliamentarians.mockResolvedValue([parliamentarian]);
  });

  it('adds a parliamentarian when the available card text is tapped', async () => {
    const onAddParlamentar = vi.fn();
    renderSelector(onAddParlamentar);

    fireEvent.click(await screen.findByText('Alan Rick'));

    expect(onAddParlamentar).toHaveBeenCalledWith(
      expect.objectContaining({
        id: '42',
        nome: 'Alan Rick',
      })
    );
  });
});
