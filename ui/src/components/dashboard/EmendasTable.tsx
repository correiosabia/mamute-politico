import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { listAmendments } from '@/api/endpoints';
import type { AmendmentOut } from '@/api/types';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { getSafeExternalUrl, openSafeExternalUrl } from '@/lib/safeExternalUrl';
import { getPortalEmendaUrl } from '@/lib/portalTransparencia';
import { getTransferegovConsultaUrl } from '@/lib/transferegov';
import { classificarTipoEmenda } from '@/lib/tipoEmenda';
import { useFeatureFlag } from '@/hooks/useFeatureFlag';
import { PlanosDeAcao } from './PlanosDeAcao';
import { ChevronDown, ChevronRight, ExternalLink, Loader2 } from 'lucide-react';

interface EmendasTableProps {
  parliamentarianId: number;
  year?: number;
}

const BRL = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL',
});

/** Valores chegam como string para não perder centavo; só viram número aqui. */
function formatBRL(value?: string | null): string {
  if (value == null || value === '') return '—';
  const parsed = Number(value);
  return Number.isFinite(parsed) ? BRL.format(parsed) : '—';
}

function textOrDash(value?: string | null): string {
  return value == null || value === '' ? '—' : value;
}

export function EmendasTable({ parliamentarianId, year }: EmendasTableProps) {
  // Portão único da feature. Nada de flag vaza para o ParlamentarDashboard —
  // ver o procedimento de remoção em `@/lib/featureFlags`.
  const prestacaoOn = useFeatureFlag('emendas_prestacao');
  const [expandida, setExpandida] = useState<string | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ['amendments', parliamentarianId, year],
    queryFn: () =>
      listAmendments({
        parliamentarian_id: parliamentarianId,
        year,
        limit: 200,
        sort_by: 'committed_value',
        sort_order: 'desc',
      }),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 py-10 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
        <span>Carregando emendas...</span>
      </div>
    );
  }

  if (isError) {
    return (
      <p className="py-10 text-center text-muted-foreground">
        Falha ao carregar as emendas do parlamentar.
      </p>
    );
  }

  if (!data || data.length === 0) {
    return (
      <p className="py-10 text-center text-muted-foreground">
        Nenhuma emenda encontrada para este parlamentar.
      </p>
    );
  }

  const colunas = prestacaoOn ? 8 : 6;

  return (
    <div className="max-h-[440px] overflow-y-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Nº</TableHead>
            {prestacaoOn && <TableHead>Tipo</TableHead>}
            <TableHead>Localidade do gasto</TableHead>
            <TableHead>Função</TableHead>
            <TableHead className="text-right">Empenhado</TableHead>
            <TableHead className="text-right">Pago</TableHead>
            {prestacaoOn && (
              <TableHead className="text-right">Prestação</TableHead>
            )}
            <TableHead className="w-[44px] text-right" aria-label="Abrir no Portal" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.map((emenda) => (
            <LinhaEmenda
              key={emenda.id}
              emenda={emenda}
              prestacaoOn={prestacaoOn}
              colunas={colunas}
              expandida={expandida === emenda.amendment_code}
              onToggle={() =>
                setExpandida((atual) =>
                  atual === emenda.amendment_code ? null : emenda.amendment_code
                )
              }
            />
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

interface LinhaEmendaProps {
  emenda: AmendmentOut;
  prestacaoOn: boolean;
  colunas: number;
  expandida: boolean;
  onToggle: () => void;
}

function LinhaEmenda({
  emenda,
  prestacaoOn,
  colunas,
  expandida,
  onToggle,
}: LinhaEmendaProps) {
  const safeLink = getSafeExternalUrl(getPortalEmendaUrl(emenda.amendment_code));
  const tipo = classificarTipoEmenda(emenda.amendment_type);
  const podeExpandir = prestacaoOn && emenda.planos_total > 0;

  // Com a feature desligada a linha inteira continua abrindo o Portal, como
  // sempre foi. Com ela ligada o clique passa a expandir, e o link externo
  // vira botão dedicado — senão as duas ações competiriam pelo mesmo clique.
  const linhaAbreOPortal = !prestacaoOn && Boolean(safeLink);

  const abrirPortal = () => openSafeExternalUrl(safeLink);
  const paineId = `planos-${emenda.amendment_code}`;

  return (
    <>
      <TableRow
        role={linhaAbreOPortal ? 'link' : podeExpandir ? 'button' : undefined}
        tabIndex={linhaAbreOPortal || podeExpandir ? 0 : -1}
        aria-expanded={podeExpandir ? expandida : undefined}
        aria-controls={podeExpandir && expandida ? paineId : undefined}
        title={
          linhaAbreOPortal
            ? 'Ver esta emenda no Portal da Transparência'
            : podeExpandir
              ? 'Ver os entes que receberam esta emenda'
              : undefined
        }
        onClick={() => {
          if (linhaAbreOPortal) abrirPortal();
          else if (podeExpandir) onToggle();
        }}
        onKeyDown={(e) => {
          if (!linhaAbreOPortal && !podeExpandir) return;
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            if (linhaAbreOPortal) abrirPortal();
            else onToggle();
          }
        }}
        className={[
          'hover:bg-muted/50',
          linhaAbreOPortal || podeExpandir
            ? 'cursor-pointer focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2'
            : 'cursor-default',
        ].join(' ')}
      >
        <TableCell className="whitespace-nowrap">
          <span className="inline-flex items-center gap-1">
            {podeExpandir &&
              (expandida ? (
                <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
              ))}
            {textOrDash(emenda.amendment_number)}
          </span>
        </TableCell>

        {prestacaoOn && (
          <TableCell className="whitespace-nowrap">
            <span
              title={tipo.oficial || undefined}
              className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-semibold text-foreground"
            >
              {tipo.rotulo}
            </span>
          </TableCell>
        )}

        <TableCell>{textOrDash(emenda.spending_locality)}</TableCell>
        <TableCell>{textOrDash(emenda.function)}</TableCell>
        <TableCell className="whitespace-nowrap text-right">
          {formatBRL(emenda.committed_value)}
        </TableCell>
        <TableCell className="whitespace-nowrap text-right">
          {formatBRL(emenda.paid_value)}
        </TableCell>

        {prestacaoOn && (
          <TableCell className="whitespace-nowrap text-right">
            <CelulaPrestacao emenda={emenda} tipoChave={tipo.chave} />
          </TableCell>
        )}

        <TableCell className="text-right">
          {safeLink &&
            (prestacaoOn ? (
              <button
                type="button"
                aria-label="Ver esta emenda no Portal da Transparência"
                title="Ver esta emenda no Portal da Transparência"
                onClick={(e) => {
                  // Sem isto o clique também alternaria a expansão da linha.
                  e.stopPropagation();
                  abrirPortal();
                }}
                className="ml-auto flex h-6 w-6 items-center justify-center rounded focus:outline-none focus:ring-2 focus:ring-ring"
              >
                <ExternalLink className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
              </button>
            ) : (
              <ExternalLink
                className="ml-auto h-4 w-4 text-muted-foreground"
                aria-hidden="true"
              />
            ))}
        </TableCell>
      </TableRow>

      {podeExpandir && expandida && (
        <TableRow>
          <TableCell colSpan={colunas} className="bg-muted/30" id={paineId}>
            <PlanosDeAcao amendmentCode={emenda.amendment_code} />
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

function CelulaPrestacao({
  emenda,
  tipoChave,
}: {
  emenda: AmendmentOut;
  tipoChave: ReturnType<typeof classificarTipoEmenda>['chave'];
}) {
  // As de Finalidade Definida são 85% da base e o Transferegov ainda não
  // publica API para elas (1ª entrega prevista para 10/2026). Dizer isso é
  // melhor que um traço mudo, que o leitor lê como erro nosso.
  if (tipoChave !== 'pix') {
    const consulta = getSafeExternalUrl(getTransferegovConsultaUrl(tipoChave));
    return (
      <span
        className="text-[12px] text-muted-foreground"
        title="O Transferegov ainda não publica API de prestação de contas para este tipo de emenda."
      >
        {consulta ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              openSafeExternalUrl(consulta);
            }}
            className="underline underline-offset-2 focus:outline-none focus:ring-2 focus:ring-ring"
          >
            não disponível
          </button>
        ) : (
          'não disponível'
        )}
      </span>
    );
  }

  if (emenda.planos_total === 0) {
    return <span className="text-[12px] text-muted-foreground">—</span>;
  }

  const todas = emenda.planos_com_prestacao === emenda.planos_total;
  return (
    <span
      className={
        todas
          ? 'text-[12px] font-semibold text-foreground'
          : 'text-[12px] text-muted-foreground'
      }
      title={`${emenda.planos_com_prestacao} de ${emenda.planos_total} entes com prestação de contas registrada`}
    >
      {emenda.planos_com_prestacao}/{emenda.planos_total}
    </span>
  );
}
