import { Mamutometro } from '@/components/selecao/Mamutometro';
import { TagChips, TagEditor } from '@/components/selecao/TagEditor';
import type {
  MamutometroState,
  TagsPessoaisState,
} from '@/hooks/useMarcacoesPessoais';

interface MarcacoesInlineProps {
  parlamentarId: string;
  parlamentarNome: string;
  /** O parlamentar está nos monitorados do projeto? Decide o escopo. */
  monitorado: boolean;
  tagsPessoais: TagsPessoaisState | null;
  mamutometro: MamutometroState | null;
  /**
   * Rótulo de seção (ex.: "Suas marcações" no perfil). Fica aqui, e não em quem
   * hospeda, porque só este componente sabe se algo vai renderizar — um rótulo
   * órfão sobre uma linha vazia é pior que nenhum.
   */
  titulo?: string;
}

/**
 * Linha de marcações pessoais de UM parlamentar: escala + chips + editor de tags.
 *
 * Reúne os mesmos componentes que a Seleção usa, com os mesmos gestos — quem
 * aprendeu lá sabe usar aqui. Não faz requisição nem lê flag: recebe o estado
 * do `useMarcacoesPessoais`, cujos `null` já carregam os dois portões (flag
 * global e plano). O que ESTA camada decide é só o escopo: com a config em
 * `monitorados` e o parlamentar de fora, o controle não renderiza — mesma
 * semântica do backend, que recusaria a escrita.
 *
 * Tudo `null`/fora de escopo => devolve null, e a tela que a hospeda fica
 * idêntica à de antes da feature.
 */
export function MarcacoesInline({
  parlamentarId,
  parlamentarNome,
  monitorado,
  tagsPessoais,
  mamutometro,
  titulo,
}: MarcacoesInlineProps) {
  const dentroDoEscopo = (escopo: 'monitorados' | 'todos') =>
    escopo === 'todos' || monitorado;

  const mostrarMamutometro =
    mamutometro != null && dentroDoEscopo(mamutometro.escopo);
  const mostrarTags = tagsPessoais != null && dentroDoEscopo(tagsPessoais.escopo);

  if (!mostrarMamutometro && !mostrarTags) return null;

  const tagIds = tagsPessoais?.tagIdsPorParlamentar[parlamentarId] ?? [];
  const tagsDoParlamentar =
    tagsPessoais?.tags.filter((tag) => tagIds.includes(tag.id)) ?? [];

  const linha = (
    <div className="flex flex-wrap items-center gap-2">
      {mostrarMamutometro && (
        <Mamutometro
          maxLevel={mamutometro.maxLevel}
          level={mamutometro.niveis[parlamentarId] ?? null}
          onChange={(nivel) => mamutometro.onChange(parlamentarId, nivel)}
          disabled={mamutometro.salvandoParlamentarId === parlamentarId}
          noticeText={mamutometro.noticeText}
          parlamentarNome={parlamentarNome}
        />
      )}
      {mostrarTags && (
        <>
          <TagChips tags={tagsDoParlamentar} />
          <TagEditor
            tags={tagsPessoais.tags}
            selectedTagIds={tagIds}
            onChange={(ids) => tagsPessoais.onAlterarTags(parlamentarId, ids)}
            onCreateTag={(nome) => tagsPessoais.onCriarTag(nome, parlamentarId)}
            disabled={tagsPessoais.salvando}
            maxTagsPerParliamentarian={tagsPessoais.maxTagsPorParlamentar}
            parlamentarNome={parlamentarNome}
          />
        </>
      )}
    </div>
  );

  if (!titulo) return linha;

  return (
    <div className="mt-4 border-t border-black/[0.06] pt-4">
      <p className="mb-2 text-[13px] font-semibold uppercase tracking-wide text-[#383838]/70">
        {titulo}
      </p>
      {linha}
    </div>
  );
}
