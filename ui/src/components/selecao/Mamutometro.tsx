import { useState } from 'react';

import logoMamute from '@/assets/logo-mamute.png';
import { Button } from '@/components/ui/button';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';

/**
 * Mamutômetro — escala pessoal de 1 a N.
 *
 * NEUTRALIDADE É REQUISITO, NÃO ESTILO. Nada aqui pode sugerir o que um nível
 * significa: cada assinante escolhe a própria regra ("3 = votei", "3 = acompanho
 * de perto", "1 = desconfio") e nunca a informa ao sistema. É isso que mantém o
 * produto longe de guardar declaração de voto.
.
 */

const CHAVE_AVISO_VISTO = 'mamutometro:aviso-visto';

interface MamutometroProps {
  /** Tamanho da régua, vindo da configuração global. */
  maxLevel: number;
  /** Nível gravado; null = sem marcação. Pode ser maior que maxLevel. */
  level: number | null;
  onChange: (level: number | null) => void;
  disabled?: boolean;
  /** Aviso neutro de primeira utilização, editável pelo painel. */
  noticeText: string;
  parlamentarNome: string;
}

export function Mamutometro({
  maxLevel,
  level,
  onChange,
  disabled = false,
  noticeText,
  parlamentarNome,
}: MamutometroProps) {
  const [avisoAberto, setAvisoAberto] = useState(false);

  // Régua reduzida pelo admin não apaga marcação: apara só a exibição, e o
  // valor gravado volta a aparecer inteiro se a régua subir de novo.
  const preenchidos = level == null ? 0 : Math.min(level, maxLevel);

  const clicar = (posicao: number) => {
    if (disabled) return;
    if (typeof window !== 'undefined' && !localStorage.getItem(CHAVE_AVISO_VISTO)) {
      setAvisoAberto(true);
      localStorage.setItem(CHAVE_AVISO_VISTO, '1');
    }
    // Clicar no nível atual limpa — é o gesto que as escalas de N posições já
    // ensinaram, e evita um segundo controle só para remover.
    onChange(posicao === level ? null : posicao);
  };

  return (
    <Popover open={avisoAberto} onOpenChange={setAvisoAberto}>
      <PopoverTrigger asChild>
        <div
          className="flex items-center gap-0.5"
          role="group"
          aria-label={`Mamutômetro de ${parlamentarNome}`}
          onClick={(e) => e.stopPropagation()}
        >
          {Array.from({ length: maxLevel }, (_, indice) => {
            const posicao = indice + 1;
            const ativo = posicao <= preenchidos;
            return (
              <Button
                key={posicao}
                type="button"
                variant="ghost"
                size="icon"
                disabled={disabled}
                className="h-7 w-7 p-0.5"
                aria-pressed={ativo}
                // Rótulo POSICIONAL: descreve a posição, nunca o que ela quer dizer.
                aria-label={`Marcar ${posicao} de ${maxLevel} em ${parlamentarNome}`}
                onClick={(e) => {
                  e.stopPropagation();
                  clicar(posicao);
                }}
              >
                <img
                  src={logoMamute}
                  alt=""
                  aria-hidden="true"
                  className={`h-4 w-4 object-contain transition-opacity ${
                    ativo ? 'opacity-100' : 'opacity-25 grayscale'
                  }`}
                />
              </Button>
            );
          })}
        </div>
      </PopoverTrigger>
      <PopoverContent
        className="w-72 text-xs leading-relaxed"
        align="start"
        onClick={(e) => e.stopPropagation()}
      >
        {noticeText}
      </PopoverContent>
    </Popover>
  );
}
