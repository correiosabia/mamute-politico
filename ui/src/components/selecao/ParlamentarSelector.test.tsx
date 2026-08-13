import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { getParliamentarianCatalogConfig, listParliamentarians } from '@/api/endpoints';
import type { ParliamentarianOut } from '@/api/types';
import type { Parlamentar } from '@/types/parlamentar';
import { ParlamentarSelector } from './ParlamentarSelector';

vi.mock('@/api/endpoints', () => ({
  getParliamentarianCatalogConfig: vi.fn(),
  listParliamentarians: vi.fn(),
}));

class MockIntersectionObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

const mockListParliamentarians = vi.mocked(listParliamentarians);
const mockGetParliamentarianCatalogConfig = vi.mocked(getParliamentarianCatalogConfig);

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

const licensedParliamentarian: ParliamentarianOut = {
  ...parliamentarian,
  status: 'Licenciado',
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
    mockGetParliamentarianCatalogConfig.mockResolvedValue({
      allowed_situations: ['exercicio'],
      default_situacao: 'exercicio',
    });
    mockListParliamentarians.mockResolvedValue([parliamentarian]);
  });

  it('uses the API catalog policy for the initial filter and available options', async () => {
    mockGetParliamentarianCatalogConfig.mockResolvedValue({
      allowed_situations: ['exercicio', 'licenciado'],
      default_situacao: 'licenciado',
    });
    mockListParliamentarians.mockResolvedValue([licensedParliamentarian]);

    renderSelector();

    await screen.findByText('Alan Rick');
    expect(mockListParliamentarians).toHaveBeenLastCalledWith(
      expect.objectContaining({ situacao: 'licenciado' }),
    );

    fireEvent.click(screen.getByRole('button', { name: /filtros/i }));
    fireEvent.click((await screen.findAllByRole('combobox'))[0]);
    expect(await screen.findByRole('option', { name: 'Em exercício' })).toBeVisible();
    expect(screen.getByRole('option', { name: 'Licenciado' })).toBeVisible();
    expect(screen.queryByRole('option', { name: 'Afastado' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('option', { name: 'Em exercício' }));
    await waitFor(() => {
      expect(mockListParliamentarians).toHaveBeenLastCalledWith(
        expect.objectContaining({ situacao: 'exercicio' }),
      );
    });
  });

  it('falls back safely to only current parliamentarians when the policy fails', async () => {
    mockGetParliamentarianCatalogConfig.mockRejectedValue(new Error('indisponível'));

    renderSelector();

    await screen.findByText('Alan Rick');
    expect(mockListParliamentarians).toHaveBeenLastCalledWith(
      expect.objectContaining({ situacao: 'exercicio' }),
    );
    expect(screen.getByRole('status')).toHaveTextContent(
      'Não foi possível carregar as opções do catálogo.',
    );
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

  it('blocks a deputado when the câmara house quota is full', async () => {
    renderSelector({
      selectorProps: {
        monitoradosQuota: {
          camara: { used: 3, limit: 3, limit_reached: true },
          senado: { used: 0, limit: 3, limit_reached: false },
        },
      },
    });

    const blockedButton = await screen.findByRole('button', {
      name: 'Limite do plano atingido para Alan Rick',
    });
    expect(blockedButton).toBeDisabled();
  });

  it('allows a deputado when only the senado house quota is full', async () => {
    const onAddParlamentar = vi.fn();
    renderSelector({
      onAddParlamentar,
      selectorProps: {
        monitoradosQuota: {
          camara: { used: 0, limit: 3, limit_reached: false },
          senado: { used: 3, limit: 3, limit_reached: true },
        },
      },
    });

    fireEvent.click(await screen.findByText('Alan Rick'));

    expect(onAddParlamentar).toHaveBeenCalledWith(
      expect.objectContaining({ id: '42', nome: 'Alan Rick' }),
    );
  });
});

const outroSelecionado: Parlamentar = {
  ...selectedParliamentarian,
  id: '43',
  nome: 'Beatriz Souza',
  nomeCompleto: 'Beatriz Souza',
};

const terceiroSelecionado: Parlamentar = {
  ...selectedParliamentarian,
  id: '44',
  nome: 'Carlos Lima',
  nomeCompleto: 'Carlos Lima',
};

describe('ParlamentarSelector — ordem pessoal (SPEC-001)', () => {
  beforeEach(() => {
    vi.stubGlobal('IntersectionObserver', MockIntersectionObserver);
    mockGetParliamentarianCatalogConfig.mockResolvedValue({
      allowed_situations: ['exercicio'],
      default_situacao: 'exercicio',
    });
    mockListParliamentarians.mockResolvedValue([]);
  });

  it('mantém a ordem recebida da API em vez de ordenar por nome', async () => {
    renderSelector({
      selectorProps: {
        parlamentaresSelecionados: [terceiroSelecionado, selectedParliamentarian, outroSelecionado],
        onReorderParlamentares: vi.fn(),
      },
    });

    const nomes = await screen.findAllByText(/Carlos Lima|Alan Rick|Beatriz Souza/);
    expect(nomes.map((n) => n.textContent)).toEqual([
      'Carlos Lima',
      'Alan Rick',
      'Beatriz Souza',
    ]);
  });

  it('envia a lista completa já reordenada ao mover para cima', async () => {
    const onReorderParlamentares = vi.fn();
    renderSelector({
      selectorProps: {
        parlamentaresSelecionados: [terceiroSelecionado, selectedParliamentarian, outroSelecionado],
        onReorderParlamentares,
      },
    });

    fireEvent.click(await screen.findByRole('button', { name: /Mover Alan Rick para cima/i }));

    expect(onReorderParlamentares).toHaveBeenCalledWith(['42', '44', '43']);
  });

  it('move para o topo em um clique', async () => {
    const onReorderParlamentares = vi.fn();
    renderSelector({
      selectorProps: {
        parlamentaresSelecionados: [terceiroSelecionado, selectedParliamentarian, outroSelecionado],
        onReorderParlamentares,
      },
    });

    fireEvent.click(
      await screen.findByRole('button', { name: /Mover Beatriz Souza para o topo/i })
    );

    expect(onReorderParlamentares).toHaveBeenCalledWith(['43', '44', '42']);
  });

  it('desabilita subir no primeiro e descer no último', async () => {
    renderSelector({
      selectorProps: {
        parlamentaresSelecionados: [terceiroSelecionado, selectedParliamentarian, outroSelecionado],
        onReorderParlamentares: vi.fn(),
      },
    });

    expect(await screen.findByRole('button', { name: /Mover Carlos Lima para cima/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Mover Beatriz Souza para baixo/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Mover Alan Rick para cima/i })).toBeEnabled();
  });

  it('sem handler (flag off): nenhum controle e ordem alfabética como antes', async () => {
    // Contrato do time: com a flag desligada a tela é idêntica à de antes da
    // feature. Aqui isso significa voltar a ordenar por nome.
    renderSelector({
      selectorProps: {
        parlamentaresSelecionados: [terceiroSelecionado, selectedParliamentarian, outroSelecionado],
      },
    });

    const nomes = await screen.findAllByText(/Carlos Lima|Alan Rick|Beatriz Souza/);
    expect(nomes.map((n) => n.textContent)).toEqual([
      'Alan Rick',
      'Beatriz Souza',
      'Carlos Lima',
    ]);
    expect(screen.queryByRole('button', { name: /Mover .* para cima/i })).not.toBeInTheDocument();
  });

  it('não mostra controles de ordem com um só monitorado', async () => {
    renderSelector({
      selectorProps: {
        parlamentaresSelecionados: [selectedParliamentarian],
        onReorderParlamentares: vi.fn(),
      },
    });

    await screen.findByText('Alan Rick');
    expect(screen.queryByRole('button', { name: /Mover .* para cima/i })).not.toBeInTheDocument();
  });
});

const TAGS = [
  { id: 7, name: 'Meio Ambiente', slug: 'meio ambiente', parliamentarian_count: 1 },
  { id: 8, name: 'Transparência', slug: 'transparencia', parliamentarian_count: 0 },
];

function renderComTags(overrides: Record<string, unknown> = {}) {
  const onAlterarTags = vi.fn();
  const onCriarTag = vi.fn();
  const onFiltrarPorTag = vi.fn();
  renderSelector({
    selectorProps: {
      parlamentaresSelecionados: [selectedParliamentarian, outroSelecionado],
      tagsPessoais: {
        tags: TAGS,
        tagIdsPorParlamentar: { '42': [7] },
        filtroTagId: null,
        maxTagsPorParlamentar: 10,
        salvando: false,
        onFiltrarPorTag,
        onAlterarTags,
        onCriarTag,
        ...overrides,
      },
    },
  });
  return { onAlterarTags, onCriarTag, onFiltrarPorTag };
}

describe('ParlamentarSelector — tags livres (SPEC-001)', () => {
  beforeEach(() => {
    vi.stubGlobal('IntersectionObserver', MockIntersectionObserver);
    mockGetParliamentarianCatalogConfig.mockResolvedValue({
      allowed_situations: ['exercicio'],
      default_situacao: 'exercicio',
    });
    mockListParliamentarians.mockResolvedValue([]);
  });

  it('sem a prop (flag off), nao mostra nada de tags', async () => {
    renderSelector({
      selectorProps: {
        parlamentaresSelecionados: [selectedParliamentarian, outroSelecionado],
      },
    });

    await screen.findByText('Alan Rick');
    expect(
      screen.queryByRole('button', { name: /Editar tags de/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText('Meio Ambiente')).not.toBeInTheDocument();
  });

  it('mostra as tags aplicadas como chip no card', async () => {
    renderComTags();

    await screen.findByText('Alan Rick');
    // Alan Rick (id 42) tem a tag 7; Beatriz (43) nao tem nenhuma.
    expect(screen.getAllByText('Meio Ambiente').length).toBeGreaterThan(0);
  });

  it('filtra a lista pela tag selecionada', async () => {
    renderComTags({ filtroTagId: 7 });

    await screen.findByText('Alan Rick');
    expect(screen.queryByText('Beatriz Souza')).not.toBeInTheDocument();
  });

  it('some com os controles de ordem enquanto filtra', async () => {
    // Ordenar com filtro enviaria lista parcial e a API responderia 422.
    renderSelector({
      selectorProps: {
        parlamentaresSelecionados: [selectedParliamentarian, outroSelecionado],
        onReorderParlamentares: vi.fn(),
        tagsPessoais: {
          tags: TAGS,
          tagIdsPorParlamentar: { '42': [7] },
          filtroTagId: 7,
          maxTagsPorParlamentar: 10,
          salvando: false,
          onFiltrarPorTag: vi.fn(),
          onAlterarTags: vi.fn(),
          onCriarTag: vi.fn(),
        },
      },
    });

    await screen.findByText('Alan Rick');
    expect(
      screen.queryByRole('button', { name: /Mover .* para cima/i }),
    ).not.toBeInTheDocument();
  });

  it('avisa quando o filtro nao casa com ninguem', async () => {
    renderComTags({ filtroTagId: 8 });

    expect(await screen.findByText('Nenhum monitorado com essa tag.')).toBeVisible();
  });

  it('marcar uma tag envia o conjunto completo', async () => {
    const { onAlterarTags } = renderComTags();

    await screen.findByText('Alan Rick');
    fireEvent.click(screen.getByRole('button', { name: /Editar tags de Alan Rick/i }));
    // O nome da tag aparece tambem nos chips de filtro; escopa ao popover.
    const popover = await screen.findByRole('dialog');
    fireEvent.click(within(popover).getByRole('button', { name: /Transparência/i }));

    expect(onAlterarTags).toHaveBeenCalledWith('42', [7, 8]);
  });
});
