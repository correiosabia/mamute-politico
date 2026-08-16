import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import {
  clearMyMamutometro,
  createMyProjectTag,
  getMarcacoesSettings,
  listMyMamutometro,
  listMyParliamentarianTags,
  listMyProjectTags,
  setMyMamutometro,
  setMyParliamentarianTags,
} from '@/api/endpoints';
import type { ParliamentarianTagsOut, ProjectTagOut } from '@/api/types';
import { ApiError } from '@/api/client';
import { useFeatureFlag } from '@/hooks/useFeatureFlag';

export const MAX_TAGS_POR_PARLAMENTAR = 10;

/**
 * Estado das tags pessoais, no shape que `ParlamentarSelector` e
 * `MarcacoesInline` consomem. `null` = feature indisponível para este usuário.
 */
export interface TagsPessoaisState {
  tags: ProjectTagOut[];
  tagIdsPorParlamentar: Record<string, number[]>;
  filtroTagId: number | null;
  maxTagsPorParlamentar: number;
  salvando: boolean;
  onFiltrarPorTag: (tagId: number | null) => void;
  onAlterarTags: (parlamentarId: string, tagIds: number[]) => void;
  onCriarTag: (nome: string, parlamentarId: string) => void;
  /** Escopo configurado no painel admin — quem consome decide se o político em tela está dentro. */
  escopo: 'monitorados' | 'todos';
}

/** Idem para o mamutômetro. `null` = flag desligada OU plano sem a feature. */
export interface MamutometroState {
  maxLevel: number;
  noticeText: string;
  niveis: Record<string, number>;
  salvando: boolean;
  /** Parlamentar cuja marcação está sendo gravada agora — só a escala dele desabilita. */
  salvandoParlamentarId: string | null;
  onChange: (parlamentarId: string, level: number | null) => void;
  escopo: 'monitorados' | 'todos';
}

export interface MarcacoesPessoais {
  tagsPessoais: TagsPessoaisState | null;
  mamutometro: MamutometroState | null;
}

/**
 * Queries + mutations das marcações pessoais (tags e mamutômetro), compartilhadas
 * entre Seleção, Dashboard Geral e perfil do parlamentar.
 *
 * DOIS portões, e os dois moram aqui para nenhuma tela repetir a regra:
 *
 * 1. **Flag global** (`feature_flag`, off/admins/all) — rollout. Lida via
 *    `useFeatureFlag`; desligada, a query nem dispara e o estado vem `null`.
 * 2. **Plano** (`feature_flag_tier` + limites do tier) — comercial. O backend
 *    resolve em `/settings/marcacoes` e devolve o RESULTADO (`enabled`,
 *    `limit`/`used` já do assinante); a tela nunca reimplementa a regra.
 *
 * `null` nos dois estados = tela idêntica à de antes da feature, que é o
 * contrato firmado nos testes de flag desligada.
 *
 * O escopo (`monitorados`/`todos`) é exposto, não aplicado: só a página sabe se
 * o político em tela está dentro dele (a Seleção lista monitorados por
 * definição; o perfil não).
 */
export function useMarcacoesPessoais(opts?: { enabled?: boolean }): MarcacoesPessoais {
  const habilitado = opts?.enabled ?? true;
  const queryClient = useQueryClient();
  const marcacoesPessoaisOn = useFeatureFlag('marcacoes_pessoais');
  const mamutometroFlagOn = useFeatureFlag('mamutometro');
  const [filtroTagId, setFiltroTagId] = useState<number | null>(null);

  const tagsQuery = useQuery({
    queryKey: ['project-tags', 'me'],
    queryFn: () => listMyProjectTags(),
    enabled: marcacoesPessoaisOn && habilitado,
  });
  const parlamentarTagsQuery = useQuery({
    queryKey: ['parliamentarian-tags', 'me'],
    queryFn: () => listMyParliamentarianTags(),
    enabled: marcacoesPessoaisOn && habilitado,
  });

  const tagIdsPorParlamentar: Record<string, number[]> = {};
  for (const linha of parlamentarTagsQuery.data ?? []) {
    tagIdsPorParlamentar[String(linha.parliamentarian_id)] = linha.tag_ids;
  }

  const avisarErroDeTag = (error: unknown, fallback: string) => {
    // 409 (tag repetida) e 422 (teto) são situações previstas, com texto pronto
    // vindo da API — informam, não alarmam.
    if (error instanceof ApiError && (error.status === 409 || error.status === 422)) {
      toast.info(error.message);
      return;
    }
    toast.error(error instanceof Error ? error.message : fallback);
  };

  const alterarTagsMutation = useMutation({
    mutationFn: ({ parlamentarId, tagIds }: { parlamentarId: string; tagIds: number[] }) =>
      setMyParliamentarianTags(Number(parlamentarId), tagIds),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['parliamentarian-tags', 'me'] });
      void queryClient.invalidateQueries({ queryKey: ['project-tags', 'me'] });
    },
    onError: (error) => avisarErroDeTag(error, 'Não foi possível salvar as tags.'),
  });

  const criarTagMutation = useMutation({
    mutationFn: ({ nome }: { nome: string; parlamentarId: string }) =>
      createMyProjectTag(nome),
    onSuccess: (tag, { parlamentarId }) => {
      void queryClient.invalidateQueries({ queryKey: ['project-tags', 'me'] });
      // As tags atuais saem do CACHE no instante do sucesso, não do closure do
      // render que disparou o mutate: criar duas tags em sequência no mesmo
      // parlamentar somava sobre uma lista velha e descartava a primeira.
      const linhas =
        queryClient.getQueryData<ParliamentarianTagsOut[]>([
          'parliamentarian-tags',
          'me',
        ]) ?? [];
      const atuais =
        linhas.find((l) => String(l.parliamentarian_id) === parlamentarId)?.tag_ids ?? [];
      alterarTagsMutation.mutate({ parlamentarId, tagIds: [...atuais, tag.id] });
    },
    onError: (error) => avisarErroDeTag(error, 'Não foi possível criar a tag.'),
  });

  // Duas condições para o mamutômetro existir: a flag (rollout) e o plano
  // (comercial). O backend já resolve a segunda em `enabled`. A query também
  // serve o `tags.escopo`, então dispara se QUALQUER uma das flags estiver
  // ligada — com as duas desligadas, nada aqui roda.
  const marcacoesSettingsQuery = useQuery({
    queryKey: ['marcacoes-settings'],
    queryFn: () => getMarcacoesSettings(),
    enabled: (mamutometroFlagOn || marcacoesPessoaisOn) && habilitado,
    staleTime: 5 * 60 * 1000,
  });
  const mamutometroConfig = marcacoesSettingsQuery.data?.mamutometro;
  const mamutometroAtivo = mamutometroFlagOn && mamutometroConfig?.enabled === true;

  const mamutometroQuery = useQuery({
    queryKey: ['mamutometro', 'me'],
    queryFn: () => listMyMamutometro(),
    enabled: mamutometroAtivo && habilitado,
  });

  const niveisPorParlamentar: Record<string, number> = {};
  for (const marca of mamutometroQuery.data ?? []) {
    niveisPorParlamentar[String(marca.parliamentarian_id)] = marca.level;
  }

  const mamutometroMutation = useMutation({
    mutationFn: async ({
      parlamentarId,
      level,
    }: {
      parlamentarId: string;
      level: number | null;
    }): Promise<void> => {
      // null = limpar. Duas rotas, um só ponto de entrada, para o componente
      // não precisar saber que "remover" é um verbo HTTP diferente.
      if (level == null) {
        await clearMyMamutometro(Number(parlamentarId));
        return;
      }
      await setMyMamutometro(Number(parlamentarId), level);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['mamutometro', 'me'] });
      // `used` faz parte da config resolvida, então ela recarrega junto.
      void queryClient.invalidateQueries({ queryKey: ['marcacoes-settings'] });
    },
    onError: (error) => {
      // 403 = teto do plano, com a mensagem de upgrade pronta vinda da API.
      if (error instanceof ApiError && (error.status === 403 || error.status === 422)) {
        toast.info(error.message);
        return;
      }
      toast.error(
        error instanceof Error ? error.message : 'Não foi possível salvar a marcação.',
      );
    },
  });

  return {
    tagsPessoais: marcacoesPessoaisOn
      ? {
          tags: tagsQuery.data ?? [],
          tagIdsPorParlamentar,
          filtroTagId,
          maxTagsPorParlamentar: MAX_TAGS_POR_PARLAMENTAR,
          salvando: alterarTagsMutation.isPending || criarTagMutation.isPending,
          onFiltrarPorTag: setFiltroTagId,
          onAlterarTags: (parlamentarId, tagIds) =>
            alterarTagsMutation.mutate({ parlamentarId, tagIds }),
          onCriarTag: (nome, parlamentarId) =>
            criarTagMutation.mutate({ nome, parlamentarId }),
          escopo: marcacoesSettingsQuery.data?.tags.escopo ?? 'todos',
        }
      : null,
    mamutometro:
      mamutometroAtivo && mamutometroConfig
        ? {
            maxLevel: mamutometroConfig.max_level,
            noticeText: mamutometroConfig.notice_text,
            niveis: niveisPorParlamentar,
            salvando: mamutometroMutation.isPending,
            salvandoParlamentarId: mamutometroMutation.isPending
              ? mamutometroMutation.variables?.parlamentarId ?? null
              : null,
            onChange: (parlamentarId, level) =>
              mamutometroMutation.mutate({ parlamentarId, level }),
            escopo: mamutometroConfig.escopo,
          }
        : null,
  };
}
