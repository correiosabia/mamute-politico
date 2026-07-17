import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { listParliamentarians } from '@/api/endpoints';
import type { ParliamentarianOut } from '@/api/types';
import type { Parlamentar } from '@/types/parlamentar';
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

type RenderSelectorOptions = {
  onAddParlamentar?: ReturnType<typeof vi.fn>;
  selectorProps?: Partial<ComponentProps<typeof ParlamentarSelector>>;
};

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

const selectedParliamentarian: Parlamentar = {
  id: '42',
  nome: 'Alan Rick',
  nomeCompleto: 'Alan Rick Miranda',
  foto: '',
  partido: { sigla: 'UNIÃO', nome: 'UNIÃO' },
  uf: 'AC',
  casa: 'camara',
  legislatura: -1,
  situacao: 'Exercício',
};

function renderSelector({
  onAddParlamentar = vi.fn(),
  selectorProps = {},
}: RenderSelectorOptions = {}) {
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
          {...selectorProps}
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
    renderSelector({ onAddParlamentar });

    fireEvent.click(await screen.findByText('Alan Rick'));

    expect(onAddParlamentar).toHaveBeenCalledWith(
      expect.objectContaining({
        id: '42',
        nome: 'Alan Rick',
      })
    );
  });

  it('shows the plan upgrade message immediately when adding is blocked by the limit', async () => {
    renderSelector({
      selectorProps: {
        monitoradosLimit: 1,
        monitoradosUsed: 1,
      },
    });

    const blockedButton = await screen.findByRole('button', {
      name: 'Limite do plano atingido para Alan Rick',
    });

    expect(blockedButton).toBeDisabled();
    expect(blockedButton).not.toHaveAttribute('title');

    fireEvent.pointerMove(blockedButton.parentElement ?? blockedButton);

    const tooltip = await screen.findByRole('tooltip');
    const tooltipContent = await screen.findByTestId('plan-limit-tooltip-content');

    expect(tooltipContent).toHaveClass('max-w-[calc(100vw-2rem)]');
    expect(within(tooltip).getByText('Limite de parlamentares atingido.')).toBeVisible();
    expect(within(tooltip).getByRole('link', { name: 'Fazer upgrade' })).toHaveAttribute(
      'href',
      '/#/portal/account/plans',
    );
  });

  it('shows a persistent upgrade CTA when the plan limit is reached', async () => {
    renderSelector({
      selectorProps: {
        monitoradosLimit: 1,
        monitoradosUsed: 1,
      },
    });

    expect(await screen.findByText('Você atingiu o limite do seu plano.')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Ver planos' })).toHaveAttribute(
      'href',
      '/#/portal/account/plans',
    );
    expect(screen.getByRole('button', { name: 'Remover um monitorado' })).toBeVisible();
  });

  it('confirms a successful add and provides direct access to the monitored parliamentarian', async () => {
    const scrollIntoView = vi.fn();
    const focus = vi.fn();
    vi.spyOn(HTMLElement.prototype, 'scrollIntoView').mockImplementation(scrollIntoView);
    vi.spyOn(HTMLElement.prototype, 'focus').mockImplementation(focus);

    renderSelector({
      selectorProps: {
        parlamentaresSelecionados: [selectedParliamentarian],
        recentlyAdded: selectedParliamentarian,
      },
    });

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Alan Rick foi adicionado aos monitorados.',
    );
    expect(screen.getByRole('button', { name: 'Abrir perfil' })).toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: 'Ver monitorados' }));

    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' });
    expect(focus).toHaveBeenCalledWith({ preventScroll: true });
  });
});
