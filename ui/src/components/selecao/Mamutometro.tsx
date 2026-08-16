import { useState } from 'react';

import iconMamute from '@/assets/icon-mamute.png';
import { JWT_TOKEN_KEY } from '@/components/auth/config';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

/**
 * Mamutômetro — escala pessoal de 1 a N.
 *
 * NEUTRALIDADE É REQUISITO, NÃO ESTILO. Nada aqui pode sugerir o que um nível
 * significa: cada assinante escolhe a própria regra ("3 = acompanho de perto",
 * "1 = desconfio") e nunca a informa ao sistema. É isso que mantém o produto
 * longe de guardar declaração de posição.
 *
 * O aviso de privacidade aparece em DUAS camadas, com papéis diferentes:
 * - tooltip no hover, sempre — contexto disponível a qualquer momento;
 * - diálogo bloqueante na primeira marcação, com confirmação explícita — a
 *   marcação só grava depois do aceite, que é o que garante a leitura de que a
 *   ADR 0002 depende. Fechar sem confirmar descarta o clique e o diálogo volta
 *   na próxima tentativa.
 */

const CHAVE_AVISO_ACEITO = 'mamutometro:aviso-aceito';

/**
 * Chave do aceite escopada pela conta (sub do JWT = e-mail): em máquina
 * compartilhada, o aceite de um assinante não vale pelo do próximo. Sem token
 * legível, cai na chave sem sufixo — quem não está logado nem consegue marcar.
 */
function chaveDoAceite(): string {
  try {
    const token = localStorage.getItem(JWT_TOKEN_KEY);
    if (!token) return CHAVE_AVISO_ACEITO;
    const payload = JSON.parse(
      atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')),
    ) as { sub?: unknown };
    const sub = typeof payload.sub === 'string' ? payload.sub.trim().toLowerCase() : '';
    return sub ? `${CHAVE_AVISO_ACEITO}:${sub}` : CHAVE_AVISO_ACEITO;
  } catch {
    return CHAVE_AVISO_ACEITO;
  }
}

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
  // Marcação aguardando o aceite do aviso. Objeto (e não número) para
  // distinguir "nada pendente" de "pendente = limpar" — a primeira interação
  // NESTE navegador pode ser limpar um nível gravado em outro.
  const [pendente, setPendente] = useState<{ nivel: number | null } | null>(null);

  // Régua reduzida pelo admin não apaga marcação: apara só a exibição, e o
  // valor gravado volta a aparecer inteiro se a régua subir de novo.
  const preenchidos = level == null ? 0 : Math.min(level, maxLevel);

  const clicar = (posicao: number) => {
    if (disabled) return;
    // Clicar no nível atual limpa — é o gesto que as escalas de N posições já
    // ensinaram, e evita um segundo controle só para remover.
    const nivel = posicao === level ? null : posicao;
    if (typeof window !== 'undefined' && !localStorage.getItem(chaveDoAceite())) {
      setPendente({ nivel });
      return;
    }
    onChange(nivel);
  };

  const confirmar = () => {
    if (pendente == null) return;
    localStorage.setItem(chaveDoAceite(), '1');
    onChange(pendente.nivel);
    setPendente(null);
  };

  return (
    <>
      <TooltipProvider delayDuration={300}>
        <Tooltip>
          <TooltipTrigger asChild>
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
                    className="h-7 w-7 cursor-pointer p-0.5"
                    aria-pressed={ativo}
                    // Rótulo POSICIONAL: descreve a posição, nunca o que ela quer dizer.
                    aria-label={`Marcar ${posicao} de ${maxLevel} em ${parlamentarNome}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      clicar(posicao);
                    }}
                  >
                    <img
                      src={iconMamute}
                      alt=""
                      aria-hidden="true"
                      className={`h-[22px] w-[22px] object-contain transition-opacity ${
                        ativo ? 'opacity-100' : 'opacity-30'
                      }`}
                    />
                  </Button>
                );
              })}
            </div>
          </TooltipTrigger>
          <TooltipContent className="max-w-72 text-xs leading-relaxed" side="top">
            {noticeText}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      {/* Radix AlertDialog não fecha por clique fora; Esc fecha e cai no
          onOpenChange(false) => descarta o clique sem gravar nem marcar o
          aceite — o diálogo volta na próxima tentativa. */}
      <AlertDialog
        open={pendente != null}
        onOpenChange={(aberto) => {
          if (!aberto) setPendente(null);
        }}
      >
        <AlertDialogContent onClick={(e) => e.stopPropagation()}>
          <AlertDialogHeader>
            <AlertDialogTitle>Antes da sua primeira marcação</AlertDialogTitle>
            <AlertDialogDescription className="text-sm leading-relaxed">
              {noticeText}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogAction onClick={confirmar}>Estou ciente</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
