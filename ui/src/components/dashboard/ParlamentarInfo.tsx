import type { ReactNode } from 'react';
import { Parlamentar } from '@/types/parlamentar';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import {
  Mail,
  Phone,
  Building2,
  MapPin,
  CircleDot,
  GraduationCap,
  Globe,
  ExternalLink,
  Share2,
} from 'lucide-react';

interface ParlamentarInfoProps {
  parlamentar: Parlamentar;
}

const BIOGRAFIA_MAX_LENGTH = 200;

function InfoGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-1.5 text-[13px] text-[#383838]">
      <p className="font-semibold text-[11px] uppercase tracking-wide text-[#383838]/60">{title}</p>
      {children}
    </div>
  );
}

function InfoRow({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <div className="flex items-start gap-2">
      <span className="mt-0.5 shrink-0 text-[#383838]/60">{icon}</span>
      <span className="min-w-0">{children}</span>
    </div>
  );
}

function ExternalLinkRow({ href, label }: { href: string; label: string }) {
  return (
    <InfoRow icon={<ExternalLink className="h-3.5 w-3.5" />}>
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="truncate text-[#1b76ff] hover:underline"
      >
        {label}
      </a>
    </InfoRow>
  );
}

function truncateBiografia(text: string): string {
  if (text.length <= BIOGRAFIA_MAX_LENGTH) return text;
  return `${text.slice(0, BIOGRAFIA_MAX_LENGTH).trimEnd()}…`;
}

export function ParlamentarInfo({ parlamentar }: ParlamentarInfoProps) {
  const situacaoLabel = parlamentar.situacao === 'Exercício' ? 'Em exercício' : parlamentar.situacao;
  const showNomeCompleto =
    parlamentar.nomeCompleto.trim().length > 0 &&
    parlamentar.nomeCompleto.trim().toLowerCase() !== parlamentar.nome.trim().toLowerCase();

  const hasMandato = parlamentar.legislatura > 0 || parlamentar.situacao;
  const hasPessoal =
    Boolean(parlamentar.naturalidade) ||
    Boolean(parlamentar.escolaridade) ||
    Boolean(parlamentar.biografiaLink) ||
    Boolean(parlamentar.biografiaTexto);
  const hasContato = Boolean(parlamentar.email) || Boolean(parlamentar.telefone) || Boolean(parlamentar.site);
  const gabinete = parlamentar.gabineteDetalhes;
  const hasGabinete =
    Boolean(gabinete?.predio) ||
    Boolean(gabinete?.sala) ||
    Boolean(gabinete?.andar) ||
    Boolean(gabinete?.nome) ||
    Boolean(parlamentar.emailGabinete);
  const hasRedesSociais = (parlamentar.redesSociais?.length ?? 0) > 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Avatar className="h-16 w-16">
          <AvatarImage src={parlamentar.foto} alt={parlamentar.nome} />
          <AvatarFallback className="text-xl bg-[#d9d9d9]">{parlamentar.nome[0]}</AvatarFallback>
        </Avatar>
        <div>
          <p className="text-[18px] font-semibold text-[#383838]">{parlamentar.nome}</p>
          {showNomeCompleto && (
            <p className="mt-0.5 text-[13px] text-[#383838]/80">{parlamentar.nomeCompleto}</p>
          )}
          <div className="mt-1 flex flex-wrap gap-1.5">
            <span
              className={`rounded px-1.5 py-0.5 text-[11px] font-bold text-white ${
                parlamentar.casa === 'camara' ? 'bg-[#1b76ff]' : 'bg-[#09e03b]'
              }`}
            >
              {parlamentar.casa === 'camara' ? 'CÂMARA' : 'SENADO'}
            </span>
            <span className="text-[11px] text-[#383838]">
              {parlamentar.partido.sigla} - {parlamentar.uf}
            </span>
          </div>
        </div>
      </div>

      {hasMandato && (
        <InfoGroup title="Mandato">
          {parlamentar.legislatura > 0 && (
            <InfoRow icon={<MapPin className="h-3.5 w-3.5" />}>
              <span>{parlamentar.legislatura}ª Legislatura</span>
            </InfoRow>
          )}
          <InfoRow icon={<CircleDot className="h-3.5 w-3.5" />}>
            <span>{situacaoLabel}</span>
          </InfoRow>
        </InfoGroup>
      )}

      {hasPessoal && (
        <InfoGroup title="Pessoal">
          {parlamentar.naturalidade && (
            <InfoRow icon={<MapPin className="h-3.5 w-3.5" />}>
              <span>{parlamentar.naturalidade}</span>
            </InfoRow>
          )}
          {parlamentar.escolaridade && (
            <InfoRow icon={<GraduationCap className="h-3.5 w-3.5" />}>
              <span>{parlamentar.escolaridade}</span>
            </InfoRow>
          )}
          {parlamentar.biografiaLink && (
            <ExternalLinkRow href={parlamentar.biografiaLink} label="Ver biografia oficial" />
          )}
          {parlamentar.biografiaTexto && (
            <InfoRow icon={<ExternalLink className="h-3.5 w-3.5" />}>
              <span>{truncateBiografia(parlamentar.biografiaTexto)}</span>
            </InfoRow>
          )}
        </InfoGroup>
      )}

      {hasContato && (
        <InfoGroup title="Contato">
          {parlamentar.email && (
            <InfoRow icon={<Mail className="h-3.5 w-3.5" />}>
              <span className="truncate">{parlamentar.email}</span>
            </InfoRow>
          )}
          {parlamentar.telefone && (
            <InfoRow icon={<Phone className="h-3.5 w-3.5" />}>
              <span>{parlamentar.telefone}</span>
            </InfoRow>
          )}
          {parlamentar.site && (
            <InfoRow icon={<Globe className="h-3.5 w-3.5" />}>
              <a
                href={parlamentar.site}
                target="_blank"
                rel="noopener noreferrer"
                className="truncate text-[#1b76ff] hover:underline"
              >
                {parlamentar.site}
              </a>
            </InfoRow>
          )}
        </InfoGroup>
      )}

      {hasGabinete && (
        <InfoGroup title="Gabinete">
          {gabinete?.predio && (
            <InfoRow icon={<Building2 className="h-3.5 w-3.5" />}>
              <span>Prédio: {gabinete.predio}</span>
            </InfoRow>
          )}
          {gabinete?.sala && (
            <InfoRow icon={<Building2 className="h-3.5 w-3.5" />}>
              <span>Sala: {gabinete.sala}</span>
            </InfoRow>
          )}
          {gabinete?.andar && (
            <InfoRow icon={<Building2 className="h-3.5 w-3.5" />}>
              <span>Andar: {gabinete.andar}</span>
            </InfoRow>
          )}
          {gabinete?.nome && (
            <InfoRow icon={<Building2 className="h-3.5 w-3.5" />}>
              <span>{gabinete.nome}</span>
            </InfoRow>
          )}
          {parlamentar.emailGabinete && (
            <InfoRow icon={<Mail className="h-3.5 w-3.5" />}>
              <span className="truncate">{parlamentar.emailGabinete}</span>
            </InfoRow>
          )}
        </InfoGroup>
      )}

      {hasRedesSociais && (
        <InfoGroup title="Redes sociais">
          {parlamentar.redesSociais?.map((rede) => (
            <InfoRow key={`${rede.name}-${rede.profileUrl}`} icon={<Share2 className="h-3.5 w-3.5" />}>
              <a
                href={rede.profileUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="truncate text-[#1b76ff] hover:underline"
              >
                {rede.name}
              </a>
            </InfoRow>
          ))}
        </InfoGroup>
      )}
    </div>
  );
}
