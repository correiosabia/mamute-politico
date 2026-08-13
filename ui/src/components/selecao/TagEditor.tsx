import { useState } from 'react';
import { Check, Plus, Tag as TagIcon, X } from 'lucide-react';

import type { ProjectTagOut } from '@/api/types';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';

export const MAX_CARACTERES_TAG = 30;

interface TagChipsProps {
  tags: ProjectTagOut[];
}

export function TagChips({ tags }: TagChipsProps) {
  if (tags.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-1">
      {tags.map((tag) => (
        <Badge
          key={tag.id}
          variant="secondary"
          className="max-w-[140px] truncate px-1.5 py-0 text-[10px] font-medium"
          title={tag.name}
        >
          {tag.name}
        </Badge>
      ))}
    </div>
  );
}

interface TagEditorProps {
  tags: ProjectTagOut[];
  selectedTagIds: number[];
  onChange: (tagIds: number[]) => void;
  onCreateTag: (name: string) => void;
  disabled?: boolean;
  maxTagsPerParliamentarian: number;
  parlamentarNome: string;
}

/**
 * Editor de tags de um parlamentar.
 *
 * Não faz requisição: recebe as tags e devolve a intenção. Quem fala com a API
 * é a página, que é onde a flag também é lida — assim o componente serve tanto
 * ao card da seleção quanto a qualquer tela futura sem arrastar dependência.
 */
export function TagEditor({
  tags,
  selectedTagIds,
  onChange,
  onCreateTag,
  disabled = false,
  maxTagsPerParliamentarian,
  parlamentarNome,
}: TagEditorProps) {
  const [busca, setBusca] = useState('');
  const [aberto, setAberto] = useState(false);

  const selecionadas = new Set(selectedTagIds);
  const noTeto = selectedTagIds.length >= maxTagsPerParliamentarian;

  const termo = busca.trim();
  const filtradas = termo
    ? tags.filter((t) => t.name.toLowerCase().includes(termo.toLowerCase()))
    : tags;
  const jaExiste = tags.some(
    (t) => t.name.toLowerCase().trim() === termo.toLowerCase(),
  );

  const alternar = (tagId: number) => {
    if (selecionadas.has(tagId)) {
      onChange(selectedTagIds.filter((id) => id !== tagId));
      return;
    }
    if (noTeto) return;
    onChange([...selectedTagIds, tagId]);
  };

  const criar = () => {
    if (!termo || jaExiste || termo.length > MAX_CARACTERES_TAG) return;
    onCreateTag(termo);
    setBusca('');
  };

  return (
    <Popover open={aberto} onOpenChange={setAberto}>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          disabled={disabled}
          className="h-7 w-7 text-muted-foreground hover:text-foreground"
          onClick={(e) => e.stopPropagation()}
          aria-label={`Editar tags de ${parlamentarNome}`}
        >
          <TagIcon className="h-4 w-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        className="w-64 p-2"
        align="end"
        onClick={(e) => e.stopPropagation()}
      >
        <Input
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              criar();
            }
          }}
          placeholder="Buscar ou criar tag"
          maxLength={MAX_CARACTERES_TAG}
          className="h-8 text-sm"
        />

        {termo && !jaExiste && (
          <Button
            variant="ghost"
            className="mt-1 h-8 w-full justify-start gap-2 text-sm"
            onClick={criar}
          >
            <Plus className="h-3.5 w-3.5" />
            <span className="truncate">Criar "{termo}"</span>
          </Button>
        )}

        <div className="mt-1 max-h-48 overflow-y-auto">
          {filtradas.length === 0 && !termo && (
            <p className="px-2 py-3 text-center text-xs text-muted-foreground">
              Você ainda não criou nenhuma tag. Digite acima para criar a primeira.
            </p>
          )}
          {filtradas.map((tag) => {
            const marcada = selecionadas.has(tag.id);
            return (
              <button
                key={tag.id}
                type="button"
                disabled={!marcada && noTeto}
                onClick={() => alternar(tag.id)}
                className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40"
              >
                <span className="flex h-4 w-4 shrink-0 items-center justify-center">
                  {marcada ? <Check className="h-3.5 w-3.5" /> : null}
                </span>
                <span className="truncate">{tag.name}</span>
              </button>
            );
          })}
        </div>

        {noTeto && (
          <p className="mt-1 px-2 text-[11px] text-muted-foreground">
            Máximo de {maxTagsPerParliamentarian} tags por parlamentar. Desmarque
            uma para escolher outra.
          </p>
        )}
      </PopoverContent>
    </Popover>
  );
}

interface TagFilterProps {
  tags: ProjectTagOut[];
  selectedTagId: number | null;
  onSelect: (tagId: number | null) => void;
}

export function TagFilter({ tags, selectedTagId, onSelect }: TagFilterProps) {
  if (tags.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {tags.map((tag) => {
        const ativa = tag.id === selectedTagId;
        return (
          <button
            key={tag.id}
            type="button"
            onClick={() => onSelect(ativa ? null : tag.id)}
            aria-pressed={ativa}
            className={`flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-medium transition-colors ${
              ativa
                ? 'border-transparent bg-[#383838] text-white'
                : 'border-black/10 bg-white text-[#383838] hover:bg-black/5'
            }`}
          >
            {tag.name}
            <span className="opacity-60">{tag.parliamentarian_count}</span>
            {ativa && <X className="h-3 w-3" />}
          </button>
        );
      })}
    </div>
  );
}
