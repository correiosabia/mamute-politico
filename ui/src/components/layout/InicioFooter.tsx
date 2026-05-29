import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';
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
  className,
}: {
  label: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'flex min-w-0 flex-col items-center gap-1.5 text-center md:gap-2 lg:items-start lg:text-left',
        className,
      )}
    >
      <span className={`${partnerLabelClass} text-[10px] md:text-[12px]`}>{label}</span>
      {children}
    </div>
  );
}

export function InicioFooter() {
  return (
    <footer className="overflow-x-hidden bg-white py-10 md:py-12">
      <div className="container flex min-w-0 flex-col gap-8 md:gap-10">
        <div className="flex min-w-0 flex-col items-center gap-8 lg:flex-row lg:items-end lg:justify-between">
          <div className="flex min-w-0 flex-col items-center gap-2 lg:items-start">
            <span className={partnerLabelClass}>Concepção</span>
            <img
              src={logoSabia}
              alt="Correio Sabiá"
              className="h-[46px] w-auto max-w-full object-contain"
            />
          </div>
          <p className="mp-footer-note min-w-0 max-w-[442px] text-center text-black lg:text-right">
            2026 Mamute Político. Dados obtidos via API aberta do Congresso Nacional.
          </p>
        </div>

        <div className="flex min-w-0 flex-col gap-10 lg:flex-row lg:items-end lg:justify-between">
          {/* Below md: 2+1 grid (centered); md+: three icons in a row; lg+: Mamute beside partners */}
          <div className="grid min-w-0 w-full grid-cols-2 gap-3 md:flex md:w-full md:shrink-0 md:justify-center md:gap-x-8 lg:w-auto lg:justify-start lg:gap-x-[45px] xl:gap-x-[54px]">
            <PartnerColumn label="Programa">
              <img
                src={logoCodesinfo}
                alt="Codesinfo"
                className="h-[36px] w-auto max-w-full object-contain md:h-[40px] md:max-w-[176px] lg:h-[44px]"
              />
            </PartnerColumn>
            <PartnerColumn label="Apoio">
              <img
                src={logoProjor}
                alt="Projor"
                className="h-[32px] w-auto max-w-full object-contain md:h-[36px] md:max-w-[161px] lg:h-[39px]"
              />
            </PartnerColumn>
            <PartnerColumn label="Financiamento" className="col-span-2 md:col-auto">
              <img
                src={logoGni}
                alt="Google News Initiative"
                className="h-[28px] w-auto max-w-full object-contain md:h-[29px] md:max-w-[215px] lg:h-[31px]"
              />
            </PartnerColumn>
          </div>
          <img
            src={logoMamute}
            alt="Mamute Político"
            className="h-[47px] w-auto max-w-full shrink-0 self-center object-contain lg:self-auto"
          />
        </div>
      </div>
    </footer>
  );
}
