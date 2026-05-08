import { Parlamentar } from '@/types/parlamentar';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Mail, Phone, Building2, MapPin, CircleDot } from 'lucide-react';

interface ParlamentarInfoProps {
  parlamentar: Parlamentar;
}

export function ParlamentarInfo({ parlamentar }: ParlamentarInfoProps) {
  const situacaoLabel = parlamentar.situacao === 'Exercício' ? 'Em exercício' : parlamentar.situacao;
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Avatar className="h-16 w-16">
          <AvatarImage src={parlamentar.foto} alt={parlamentar.nome} />
          <AvatarFallback className="text-xl bg-[#d9d9d9]">{parlamentar.nome[0]}</AvatarFallback>
        </Avatar>
        <div>
          <p className="text-[18px] font-semibold text-[#383838]">{parlamentar.nome}</p>
          <div className="flex flex-wrap gap-1.5 mt-1">
            <span
              className={`rounded px-1.5 py-0.5 text-[11px] font-bold text-white ${
                parlamentar.casa === 'camara' ? 'bg-[#1b76ff]' : 'bg-[#09e03b]'
              }`}
            >
              {parlamentar.casa === 'camara' ? 'CÂMARA' : 'SENADO'}
            </span>
            <span className="text-[11px] text-[#383838]">{parlamentar.partido.sigla} - {parlamentar.uf}</span>
          </div>
        </div>
      </div>

      <div className="space-y-1.5 text-[13px] text-[#383838]">
        <p className="font-semibold text-[11px] uppercase tracking-wide text-[#383838]/60">Informações</p>
        <div className="flex items-center gap-2">
          <MapPin className="h-3.5 w-3.5 text-[#383838]/60" />
          <span>{parlamentar.legislatura}ª Legislatura</span>
        </div>
        <div className="flex items-center gap-2">
          <CircleDot className="h-3.5 w-3.5 text-[#383838]/60" />
          <span>{situacaoLabel}</span>
        </div>
        {parlamentar.email && (
          <div className="flex items-center gap-2">
            <Mail className="h-3.5 w-3.5 text-[#383838]/60" />
            <span className="truncate">{parlamentar.email}</span>
          </div>
        )}
        {parlamentar.telefone && (
          <div className="flex items-center gap-2">
            <Phone className="h-3.5 w-3.5 text-[#383838]/60" />
            <span>{parlamentar.telefone}</span>
          </div>
        )}
        {parlamentar.gabinete && (
          <div className="flex items-center gap-2">
            <Building2 className="h-3.5 w-3.5 text-[#383838]/60" />
            <span>{parlamentar.gabinete}</span>
          </div>
        )}
      </div>
    </div>
  );
}
