import type { ReactNode } from 'react';
import logoMamute from '@/assets/logo-mamute.png';
import logoSabia from '@/assets/footer-logo-sabia.png';
import logoCodesinfo from '@/assets/footer-logo-codesinfo.png';
import logoProjor from '@/assets/footer-logo-projor.png';
import logoGni from '@/assets/footer-logo-gni.png';

const partnerLabelClass =
  'text-[12px] font-bold uppercase leading-normal text-[#c3c3c3]';

function PartnerColumn({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5 sm:gap-2">
      <span className={`${partnerLabelClass} text-[10px] sm:text-[12px]`}>{label}</span>
      {children}
    </div>
  );
}

export function InicioFooter() {
  return (
    <footer className="bg-white py-10 md:py-12">
      <div className="container flex flex-col gap-8 md:gap-10">
        <div className="flex flex-col gap-8 md:flex-row md:items-end md:justify-between">
          <div className="flex flex-col gap-2">
            <span className={partnerLabelClass}>Concepção</span>
            <img
              src={logoSabia}
              alt="Correio Sabiá"
              className="h-[46px] w-auto max-w-[212px] object-contain object-left"
            />
          </div>
          <p className="mp-footer-note max-w-[442px] shrink-0 text-black md:text-right">
            2026 Mamute Político. Dados obtidos via API aberta do Congresso Nacional.
          </p>
        </div>

        <div className="flex flex-col gap-10 md:flex-row md:items-end md:justify-between">
          <div className="grid w-full grid-cols-3 gap-3 sm:gap-6">
            <PartnerColumn label="Programa">
              <img
                src={logoCodesinfo}
                alt="Codesinfo"
                className="h-[28px] w-full max-w-[176px] object-contain object-left sm:h-[44px]"
              />
            </PartnerColumn>
            <PartnerColumn label="Apoio">
              <img
                src={logoProjor}
                alt="Projor"
                className="h-[24px] w-full max-w-[161px] object-contain object-left sm:h-[39px]"
              />
            </PartnerColumn>
            <PartnerColumn label="Financiamento">
              <img
                src={logoGni}
                alt="Google News Initiative"
                className="h-[20px] w-full max-w-[215px] object-contain object-left sm:h-[31px]"
              />
            </PartnerColumn>
          </div>
          <img
            src={logoMamute}
            alt="Mamute Político"
            className="h-[47px] w-auto self-start md:self-auto md:shrink-0"
          />
        </div>
      </div>
    </footer>
  );
}
