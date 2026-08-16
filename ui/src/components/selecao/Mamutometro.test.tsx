import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

import { Mamutometro } from './Mamutometro';

function renderEscala(props: Partial<React.ComponentProps<typeof Mamutometro>> = {}) {
  const onChange = vi.fn();
  const { unmount } = render(
    <Mamutometro
      maxLevel={3}
      level={null}
      onChange={onChange}
      noticeText="Aqui que sua vida começa a mudar."
      parlamentarNome="Jane Doe"
      {...props}
    />,
  );
  return { onChange, unmount };
}

const CHAVE_AVISO_ACEITO = 'mamutometro:aviso-aceito';

/** Simula quem já confirmou o aviso — o caminho dos testes de marcação. */
function aceitarAviso() {
  localStorage.setItem(CHAVE_AVISO_ACEITO, '1');
}

describe('Mamutometro', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('renderiza uma posição por mamute da régua', () => {
    renderEscala({ maxLevel: 5 });

    expect(screen.getAllByRole('button', { name: /Marcar \d de 5/i })).toHaveLength(5);
  });

  it('marca o nível clicado', () => {
    aceitarAviso();
    const { onChange } = renderEscala();

    fireEvent.click(screen.getByRole('button', { name: /Marcar 2 de 3/i }));

    expect(onChange).toHaveBeenCalledWith(2);
  });

  it('clicar no nível atual limpa a marcação', () => {
    aceitarAviso();
    const { onChange } = renderEscala({ level: 2 });

    fireEvent.click(screen.getByRole('button', { name: /Marcar 2 de 3/i }));

    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('primeira marcação: abre o diálogo e NÃO grava antes do aceite', () => {
    const { onChange } = renderEscala();

    fireEvent.click(screen.getByRole('button', { name: /Marcar 2 de 3/i }));

    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    expect(screen.getByText('Aqui que sua vida começa a mudar.')).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });

  it('"Estou ciente" grava a marcação pendente e não pergunta de novo', () => {
    const { onChange } = renderEscala();

    fireEvent.click(screen.getByRole('button', { name: /Marcar 2 de 3/i }));
    fireEvent.click(screen.getByRole('button', { name: 'Estou ciente' }));

    expect(onChange).toHaveBeenCalledWith(2);
    expect(localStorage.getItem(CHAVE_AVISO_ACEITO)).toBe('1');

    // Próximo clique vai direto, sem diálogo.
    fireEvent.click(screen.getByRole('button', { name: /Marcar 3 de 3/i }));
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(onChange).toHaveBeenCalledWith(3);
  });

  it('fechar o diálogo sem confirmar descarta o clique e pergunta de novo', () => {
    const { onChange } = renderEscala();

    fireEvent.click(screen.getByRole('button', { name: /Marcar 2 de 3/i }));
    fireEvent.keyDown(screen.getByRole('alertdialog'), { key: 'Escape' });

    expect(onChange).not.toHaveBeenCalled();
    expect(localStorage.getItem(CHAVE_AVISO_ACEITO)).toBeNull();

    // Sem aceite registrado, a próxima tentativa reabre o diálogo.
    fireEvent.click(screen.getByRole('button', { name: /Marcar 1 de 3/i }));
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });

  it('o aceite é por conta: JWT de outro assinante não herda o aceite anterior', () => {
    const jwtDe = (sub: string) =>
      `h.${btoa(JSON.stringify({ sub })).replace(/\+/g, '-').replace(/\//g, '_')}.s`;

    localStorage.setItem('mamutePoliticoJwtToken', jwtDe('primeira@conta.com'));
    const primeira = renderEscala();
    fireEvent.click(screen.getByRole('button', { name: /Marcar 2 de 3/i }));
    fireEvent.click(screen.getByRole('button', { name: 'Estou ciente' }));
    expect(primeira.onChange).toHaveBeenCalledWith(2);
    primeira.unmount();

    // Troca de conta na mesma máquina: o aviso precisa aparecer de novo.
    localStorage.setItem('mamutePoliticoJwtToken', jwtDe('segunda@conta.com'));
    const segunda = renderEscala();
    fireEvent.click(screen.getByRole('button', { name: /Marcar 2 de 3/i }));
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    expect(segunda.onChange).not.toHaveBeenCalled();
  });

  it('nível acima da régua aparece aparado, sem perder o valor', () => {
    // Admin reduziu a escala depois de o assinante marcar 5.
    renderEscala({ maxLevel: 3, level: 5 });

    const posicoes = screen.getAllByRole('button', { name: /Marcar \d de 3/i });
    expect(posicoes).toHaveLength(3);
    expect(posicoes.every((b) => b.getAttribute('aria-pressed') === 'true')).toBe(true);
  });

  it('os rótulos de acessibilidade são posicionais, nunca semânticos', () => {
    renderEscala({ level: 1 });

    for (const botao of screen.getAllByRole('button')) {
      const rotulo = (botao.getAttribute('aria-label') ?? '').toLowerCase();
      expect(rotulo).toMatch(/marcar \d de \d/);
      for (const proibido of ['voto', 'votei', 'apoio', 'afinidade', 'prefer']) {
        expect(rotulo).not.toContain(proibido);
      }
    }
  });
});

describe('Mamutometro — neutralidade da copy (SPEC-001)', () => {
  it('o componente não contém palavra que atribua significado a um nível', () => {
    // Este é o teste que segura a garantia inteira da feature: o significado de
    // cada nível é de quem usa, e o dia em que a tela disser o que 3 quer dizer,
    // o sistema passa a guardar aquilo. Se este teste falhar, ou a copy voltou
    // atrás, ou o desenho mudou — e aí a spec muda junto.
    const arquivo = path.join(__dirname, 'Mamutometro.tsx');
    const codigo = fs.readFileSync(arquivo, 'utf-8');

    // Só o que a pessoa lê na tela: strings de JSX e rótulos, não comentários,
    // que precisam justamente falar sobre o que NÃO pode aparecer.
    const semComentarios = codigo
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/^\s*\/\/.*$/gm, '');

    for (const proibido of ['voto', 'votei', 'votar', 'apoio', 'afinidade', 'prefer']) {
      expect(semComentarios.toLowerCase()).not.toContain(proibido);
    }
  });
});
