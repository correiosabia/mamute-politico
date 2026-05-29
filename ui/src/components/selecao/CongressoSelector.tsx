import { useState } from 'react';
import { CasaLegislativa } from '@/types/parlamentar';
import texturaBackground from '@/assets/textura.png';
import congressoRecorte from '@/assets/banner2-semfundo.png';
import { SelecaoFooter } from '@/components/selecao/SelecaoFooter';

interface CongressoSelectorProps {
  onSelect: (casa: CasaLegislativa) => void;
  selected: CasaLegislativa | null;
}

export function CongressoSelector({ onSelect, selected }: CongressoSelectorProps) {
  const PERSPECTIVE_PX = 1200;
  const MAX_ROTATE_Y_DEG = 2;
  const MAX_TRANSLATE_X_PX = 20;
  const BACKGROUND_SCALE = 1.02;

  const buildTransform = (centered: number) =>
    `perspective(${PERSPECTIVE_PX}px) rotateY(${(centered * -MAX_ROTATE_Y_DEG).toFixed(2)}deg) translateX(${(centered * -MAX_TRANSLATE_X_PX).toFixed(2)}px) scale(${BACKGROUND_SCALE})`;

  // -1 = full left tilt, 0 = centered, 1 = full right tilt
  const [tilt, setTilt] = useState(0);
  const [isHovering, setIsHovering] = useState(false);
  const imageTransform = buildTransform(tilt);

  const tiltMap: Record<CasaLegislativa, number> = {
    senado: -1,
    ambas: 0,
    camara: 1,
  };

  const options: Array<{ key: CasaLegislativa; label: string }> = [
    { key: 'senado', label: 'SENADO FEDERAL' },
    { key: 'ambas', label: 'AMBAS AS CASAS' },
    { key: 'camara', label: 'CÂMARA DOS DEPUTADOS' },
  ];
  const optionIdMap: Record<CasaLegislativa, string> = {
    senado: 'senado-federal',
    ambas: 'ambas-casas',
    camara: 'camara-dos-deputados',
  };

  return (
    <>
    <section
      className="relative min-h-[calc(800px)] overflow-hidden bg-textura-gold"
    >
      <img
        src={texturaBackground}
        alt=""
        aria-hidden="true"
        className="absolute inset-0 h-full w-full object-cover object-bottom"
      />
      <div
        className="absolute inset-0 h-full w-[101.25%] transition-transform duration-500 ease-in-out"
        style={{ transform: imageTransform, transformOrigin: 'center bottom' }}
      >
        <img
          src={congressoRecorte}
          alt="Congresso Nacional"
          className="absolute bottom-0 left-0 w-full object-contain object-bottom"
        />

      </div>

      {/* textura over right side when Senado (left) is hovered */}
      <div
        className="pointer-events-none absolute inset-0 transition-opacity duration-500 ease-in-out"
        style={{
          opacity: tilt < 0 || !isHovering ? 0.5 : 0,
          maskImage: 'linear-gradient(to left, black 47%, transparent 53%)',
          WebkitMaskImage: 'linear-gradient(to left, black 47%, transparent 53%)',
        }}
      >
        <img src={texturaBackground} alt="" aria-hidden className="h-full w-full object-cover object-bottom" />
      </div>
      {/* textura over left side when Câmara (right) is hovered */}
      <div
        className="pointer-events-none absolute inset-0 transition-opacity duration-500 ease-in-out"
        style={{
          opacity: tilt > 0 || !isHovering ? 0.5 : 0,
          maskImage: 'linear-gradient(to right, black 47%, transparent 53%)',
          WebkitMaskImage: 'linear-gradient(to right, black 47%, transparent 53%)',
        }}
      >
        <img src={texturaBackground} alt="" aria-hidden className="h-full w-full object-cover object-bottom" />
      </div>

      <div className="relative flex min-h-[calc(100vh-88px)] flex-col py-14 px-6">
        <div className="space-y-3 text-center">
          <h2 className="text-[36px] md:text-[48px] leading-none font-bold text-[#393939]">
            Selecione a Casa Legislativa
          </h2>
          <p className="mx-auto max-w-2xl text-[18px] font-normal text-[#383838]">
            Escolha qual casa legislativa você deseja acompanhar.
            <br />
            Você pode selecionar a Câmara dos Deputados, o Senado Federal, ou ambas.
          </p>
        </div>

        <div className="mx-auto mt-14 flex w-fit max-w-full flex-col items-center justify-center gap-3 md:flex-row md:flex-wrap">
          {options.map((option) => {
            const isActive = selected === option.key;
            return (
              <button
                key={option.key}
                id={optionIdMap[option.key]}
                type="button"
                onClick={() => onSelect(option.key)}
                onMouseEnter={() => { setTilt(tiltMap[option.key]); setIsHovering(true); }}
                onMouseLeave={() => { setTilt(0); setIsHovering(false); }}
                className={`w-[194px] shrink-0 rounded-[76px] py-2.5 text-[13px] font-semibold uppercase tracking-wide shadow-sm transition ${
                  isActive ? 'bg-[#1b76ff] text-white' : 'bg-white text-[#383838] hover:bg-[#1b76ff] hover:text-white'
                }`}
              >
                {option.label}
              </button>
            );
          })}
        </div>

      </div>

    </section>
    <SelecaoFooter />
    </>
  );
}
