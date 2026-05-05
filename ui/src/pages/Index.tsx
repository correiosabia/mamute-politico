import { useRef, useState, type MouseEventHandler } from 'react';
import { Link } from 'react-router-dom';
import { Header } from '@/components/layout/Header';
import texturaBackground from '@/assets/textura.png';
import congressoForeground from '@/assets/banner1-semfundo.png';
import mammothImage from '@/assets/figma-mamute.png';
import logoMamute from '@/assets/logo-mamute.png';
import iconFuncionalidades from '@/assets/icon-funcionalidades.svg';
import iconDeputados from '@/assets/icon-deputados.svg';
import iconSenadores from '@/assets/icon-senadores.svg';
import iconProposicoes from '@/assets/icon-proposicoes.svg';
import iconVotacoes from '@/assets/icon-votacoes.svg';

const TempoRealIcon = () => (
  <svg viewBox="0 0 41 29" aria-hidden="true" className="h-[18px] w-[26px]">
    <g fill="none" stroke="#393939" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.4">
      <path d="M6 10.5h9" />
      <path d="M2 16h9" />
      <path d="M19 4h8" />
      <path d="M23 1.6v4.1" />
      <circle cx="23" cy="17.6" r="10.6" />
      <path d="M23 11.8v6.2" />
    </g>
  </svg>
);

const features = [
  {
    title: 'ACOMPANHAMENTO\nPERSONALIZADO',
    description: 'Selecione e monitore os parlamentares do seu interesse.',
  },
  {
    title: 'DASHBOARD\nINTERATIVO',
    description: 'Visualize dados, votações e proposições em tempo real.',
  },
  {
    title: 'PESQUISA POR IA',
    description: 'Consulte informações legislativas em linguagem natural.',
  },
  {
    title: 'NOTIFICAÇÕES',
    description: 'Receba alertas sobre movimentações dos parlamentares.',
  },
];

const stats = [
  { label: 'DEPUTADOS/AS', value: '513', iconSrc: iconDeputados, iconAlt: 'Ícone de deputados', liftIconOnHover: true },
  { label: 'SENADORES/AS', value: '81', iconSrc: iconSenadores, iconAlt: 'Ícone de senadores', liftIconOnHover: true },
  { label: 'PROPOSIÇÕES 2024', value: '4.532', iconSrc: iconProposicoes, iconAlt: 'Ícone de proposições', liftIconOnHover: true },
  { label: 'VOTAÇÕES', value: '892', iconSrc: iconVotacoes, iconAlt: 'Ícone de votações', liftIconOnHover: true },
];

const Index = () => {
  const HERO_PERSPECTIVE_PX = 1200;
  const HERO_MAX_ROTATE_Y_DEG = 2;
  const HERO_MAX_TRANSLATE_X_PX = 22;
  const HERO_SCALE = 1.02;
  const heroContainerRef = useRef<HTMLElement | null>(null);

  const [heroTransform, setHeroTransform] = useState(
    `perspective(${HERO_PERSPECTIVE_PX}px) rotateY(0deg) translateX(0px) scale(${HERO_SCALE})`
  );

  const handleHeroMouseMove: MouseEventHandler<HTMLElement> = (event) => {
    const rect = heroContainerRef.current?.getBoundingClientRect() ?? event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width;
    const clampedX = Math.min(1, Math.max(0, x));
    const centered = (clampedX - 0.5) * 2;

    const rotateY = centered * -HERO_MAX_ROTATE_Y_DEG;
    const translateX = centered * -HERO_MAX_TRANSLATE_X_PX;
    setHeroTransform(
      `perspective(${HERO_PERSPECTIVE_PX}px) rotateY(${rotateY.toFixed(2)}deg) translateX(${translateX.toFixed(2)}px) scale(${HERO_SCALE})`
    );
  };

  const handleHeroMouseLeave = () => {
    setHeroTransform(
      `perspective(${HERO_PERSPECTIVE_PX}px) rotateY(0deg) translateX(0px) scale(${HERO_SCALE})`
    );
  };

  return (
    <div className="min-h-screen font-sans bg-white">
      <div className="bg-textura-gold">
        <Header />

        <section
          ref={heroContainerRef}
          className="relative overflow-hidden"
          onMouseMove={handleHeroMouseMove}
          onMouseLeave={handleHeroMouseLeave}
        >
          <img
            src={texturaBackground}
            alt=""
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 h-full w-full object-cover object-center"
          />
          <div
            className="pointer-events-none absolute inset-0 h-full w-full"
            style={{ transform: heroTransform, transformOrigin: 'center center' }}
          >
            <img
              src={congressoForeground}
              alt=""
              className="absolute right-0 bottom-0 w-full object-cover object-center"
            />
          </div>

          <div className="container relative z-10 grid min-h-[700px] md:min-h-[560px] 2xl:min-h-[800px] items-center py-8">
            <div className="max-w-[610px] space-y-5">
              <p className="flex items-center gap-2 text-[15px] font-extrabold italic leading-normal tracking-[0.02em] text-[#393939] uppercase">
                <TempoRealIcon />
                TEMPO REAL
              </p>
              <h1 className="text-[48px] font-bold leading-[1.08] text-[#393939]">
                Monitore políticos do Congresso
              </h1>
              <p className="max-w-[565px] text-[18px] font-normal leading-normal text-[#393939]">
              Memória de elefante: saiba como vota, o que propõe e até o que diz em discurso o(s) congressista(s) da sua escolha.
              </p>
              <div className="flex flex-wrap gap-4 pt-2">
                <Link
                  to="/selecao"
                  className="inline-flex h-9 items-center rounded-[76px] bg-[#ff0004] px-9 text-[13px] font-bold uppercase leading-normal tracking-normal text-white transition hover:opacity-90"
                >
                    COMEÇAR AGORA
                </Link>
                <Link to="/dashboard" className="mp-pill-light inline-flex h-9 items-center px-7 text-[13px] font-semibold uppercase leading-normal tracking-normal text-[#4b4b4b] transition hover:opacity-90">
                    EXPLORAR DASHBOARD
                </Link>
              </div>
            </div>
          </div>
        </section>
      </div>

      <section className="pb-16 relative z-10">
        <div className="container mt-4 md:-mt-12">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {stats.map((stat) => (
              <div
                key={stat.label}
                className="group mp-card flex h-[285px] flex-col items-center justify-center gap-3 bg-white p-4 text-center transition-all duration-300 ease-out hover:-translate-y-2 hover:shadow-[0_14px_24px_rgba(0,0,0,0.22)]"
              >
                {stat.iconSrc ? (
                  <img
                    src={stat.iconSrc}
                    alt={stat.iconAlt}
                    className={`h-auto w-auto max-h-[96px] max-w-[clamp(64px,18vw,96px)] object-contain transition-transform duration-300 ease-out ${
                      stat.liftIconOnHover ? 'group-hover:-translate-y-1' : ''
                    }`}
                  />
                ) : null}
                <p className="text-[36px] font-extrabold leading-none text-[#878787]">{stat.value}</p>
                <p className="text-[14px] font-normal uppercase tracking-normal text-black">{stat.label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-white pb-20 pt-2">
        <div className="container">
          <div className="mb-10 text-center lg:text-right">
            <h2 className="mb-3 text-[40px] font-bold text-[#090909]">
              Funcionalidades Principais
            </h2>
            <p className="ml-auto max-w-2xl text-[20px] font-normal text-[#090909]">
              Ferramentas poderosas para você acompanhar e analisar a atividade legislativa brasileira de forma <strong>simples e eficiente</strong>.
            </p>
          </div>

          <div className="grid items-end gap-8 lg:grid-cols-2">
            <div className="flex justify-center lg:justify-start">
              <img src={mammothImage} alt="Mamute ilustração" className="h-auto w-[780px] lg:max-w-none max-w-full object-contain lg:-ml-24" />
            </div>
            <div className="grid gap-4 grid-cols-1 md:grid-cols-2">
              {features.map((feature) => (
                <div
                  key={feature.title}
                  className="group mp-card flex min-h-[254px] flex-col items-center gap-4 bg-white p-6 text-center transition-all duration-300 ease-out hover:-translate-y-2 hover:shadow-[0_14px_24px_rgba(0,0,0,0.22)]"
                >
                  <img
                    src={iconFuncionalidades}
                    alt=""
                    aria-hidden="true"
                    className="h-16 w-16 object-contain transition-transform duration-500 ease-out group-hover:rotate-[360deg]"
                  />
                  <h3 className="text-[15px] font-bold uppercase text-[#4b4b4b] whitespace-pre-line leading-tight">
                    {feature.title}
                  </h3>
                  <p className="text-[16px] font-normal text-[#000000]">{feature.description}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="bg-white py-12">
        <div className="container text-center">
          <h2 className="mb-4 text-[56px] font-bold text-[#080808]">
            Pronto para começar?
          </h2>
          <p className="mx-auto mb-8 max-w-2xl text-[18px] font-semibold text-[#080808]">
            Selecione os parlamentares que deseja acompanhar e comece a monitorar suas atividades legislativas agora mesmo.
          </p>
          <Link to="/selecao" className="inline-flex rounded-[76px] bg-[#468fff] px-8 py-3 text-[15px] font-bold uppercase tracking-wide text-white transition hover:opacity-90">
              SELECIONAR PARLAMENTARES
          </Link>
        </div>
      </section>

      <footer className="bg-white py-8">
        <div className="container flex flex-col items-center justify-between gap-4 md:flex-row">
          <img src={logoMamute} alt="Mamute Político" className="h-[47px] w-auto" />
          <p className="mp-footer-note text-black">
            2026 Mamute Político. Dados obtidos via API aberta do Congresso Nacional.
          </p>
        </div>
      </footer>
    </div>
  );
};

export default Index;
