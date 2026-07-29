import { useMemo, useState } from 'react';
import { Plus, Search, X } from 'lucide-react';

import { normalizeWordCloudTerm } from '@/components/dashboard/wordCloudTerms';

interface TermListEditorProps {
  title: string;
  /** Explica o efeito deste filtro — usar o errado quebra a nuvem. */
  description: string;
  example: string;
  terms: string[];
  onChange: (terms: string[]) => void;
}

/** Editor de uma lista de termos: adicionar, remover e buscar. */
export function TermListEditor({
  title,
  description,
  example,
  terms,
  onChange,
}: TermListEditorProps) {
  const [draft, setDraft] = useState('');
  const [search, setSearch] = useState('');

  const visible = useMemo(() => {
    const needle = normalizeWordCloudTerm(search);
    return needle ? terms.filter((t) => t.includes(needle)) : terms;
  }, [terms, search]);

  const add = () => {
    const term = normalizeWordCloudTerm(draft);
    setDraft('');
    if (!term || terms.includes(term)) return;
    onChange([...terms, term].sort());
  };

  return (
    <section aria-label={title} className="mp-card flex flex-col gap-4 bg-white p-6">
      <div>
        <h2 className="text-[20px] font-bold leading-tight text-[#090909]">{title}</h2>
        <p className="mt-1 text-[13px] leading-relaxed text-[#383838]">{description}</p>
        <p className="mt-1 text-[12px] italic text-[#383838]/60">{example}</p>
      </div>

      <div className="flex gap-2">
        <input
          aria-label={`Adicionar termo em ${title}`}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              add();
            }
          }}
          placeholder="Digite um termo e Enter"
          className="min-w-0 flex-1 rounded-full border border-[#383838]/15 px-4 py-2 text-[13px] text-[#383838] outline-none focus-visible:border-[#1b76ff]"
        />
        <button
          type="button"
          onClick={add}
          aria-label={`Adicionar em ${title}`}
          className="flex shrink-0 items-center gap-1 rounded-full bg-[#1b76ff] px-4 py-2 text-[13px] font-semibold text-white transition-opacity hover:opacity-90"
        >
          <Plus className="h-4 w-4" aria-hidden />
          Adicionar
        </button>
      </div>

      {terms.length > 8 && (
        <div className="relative">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#383838]/40"
            aria-hidden
          />
          <input
            aria-label={`Buscar em ${title}`}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar"
            className="w-full rounded-full border border-[#383838]/15 py-2 pl-9 pr-4 text-[13px] outline-none focus-visible:border-[#1b76ff]"
          />
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        {visible.length === 0 ? (
          <p className="text-[13px] text-[#383838]/50">
            {terms.length === 0 ? 'Nenhum termo cadastrado.' : 'Nada encontrado na busca.'}
          </p>
        ) : (
          visible.map((term) => (
            <span
              key={term}
              className="inline-flex items-center gap-1.5 rounded-full bg-[#1b76ff]/10 py-1 pl-3 pr-1.5 text-[13px] text-[#090909]"
            >
              {term}
              <button
                type="button"
                aria-label={`Remover ${term}`}
                onClick={() => onChange(terms.filter((t) => t !== term))}
                className="flex h-5 w-5 items-center justify-center rounded-full text-[#383838]/50 transition-colors hover:bg-[#1b76ff]/20 hover:text-[#090909]"
              >
                <X className="h-3.5 w-3.5" aria-hidden />
              </button>
            </span>
          ))
        )}
      </div>

      <p className="mt-auto text-[12px] text-[#383838]/50">
        {terms.length} termo{terms.length === 1 ? '' : 's'}
      </p>
    </section>
  );
}
