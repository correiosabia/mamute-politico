import logoMamute from '@/assets/logo-mamute.png';

/**
 * Rodapé da busca de candidaturas: fundo claro, logo escura à esquerda e
 * copyright à direita — sem a faixa verde do `SelecaoFooter` (design v2, 17/08).
 */
export function CandidaturasFooter() {
  return (
    <footer className="border-t border-black/5 bg-[#f1f1f1] py-10">
      <div className="container">
        <div className="flex flex-col items-center justify-between gap-6 px-2 text-[12px] font-medium text-[#7f7b7b] md:flex-row">
          <img src={logoMamute} alt="Mamute Político" className="h-[30px] w-auto" />
          <span className="text-center md:text-right">
            © 2026 Mamute Político. Dados obtidos via API aberta do Congresso Nacional.
          </span>
        </div>
      </div>
    </footer>
  );
}
