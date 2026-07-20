import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Loader2 } from 'lucide-react';
import { AdminShell } from '@/components/layout/AdminShell';
import { useTiers, useUpdateTier } from '@/hooks/useTiers';
import type { Tier, TierDetails } from '@/api/admin';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useToast } from '@/components/ui/use-toast';

type FieldType = 'number' | 'list' | 'multiselect';

interface FieldDef {
  key: string;
  label: string;
  hint?: string;
  type: FieldType;
  step?: string;
  options?: { value: string; label: string }[];
  /** Só-leitura: sincronizado do Ghost, não editável nem enviado no PUT. */
  readOnly?: boolean;
}

// Valores canônicos que o envio (mamute_scrappers.scripts.notificacao) entende.
const PERIODICITY_OPTIONS = [
  { value: 'day', label: 'Diário' },
  { value: 'week', label: 'Semanal' },
  { value: 'fortnight', label: 'Quinzenal' },
  { value: 'month', label: 'Mensal' },
];

const GROUPS: { title: string; fields: FieldDef[] }[] = [
  {
    title: 'Limites do plano',
    fields: [
      { key: 'qtd_termos_camara', label: 'Monitorados — Câmara', hint: 'Máximo de deputados por plano', type: 'number' },
      { key: 'qtd_termos_senado', label: 'Monitorados — Senado', hint: 'Máximo de senadores por plano', type: 'number' },
      { key: 'qtd_consultas_ia_mes', label: 'Consultas de IA / mês', hint: 'Teto mensal do chatbot', type: 'number' },
      { key: 'qtd_consultas_ia_semana', label: 'Consultas de IA / semana', hint: 'Limite semanal (opcional; vale junto com o mensal). Vazio = sem limite semanal', type: 'number' },
      { key: 'preco_mensal', label: 'Preço mensal (R$)', hint: 'Sincronizado do Ghost — base da margem', type: 'number', step: '0.01', readOnly: true },
    ],
  },
  {
    title: 'E-mails e órgãos',
    fields: [
      { key: 'periodicidade_email', label: 'Periodicidade de e-mail', hint: 'Frequências de relatório que este plano recebe', type: 'multiselect', options: PERIODICITY_OPTIONS },
      { key: 'orgao', label: 'Órgãos', hint: 'Separe por vírgula — ainda não usado', type: 'list' },
    ],
  },
];

const isListLike = (t: FieldType) => t === 'list' || t === 'multiselect';

const ALL_FIELDS = GROUPS.flatMap((g) => g.fields);

function initialForm(tier: Tier): Record<string, string> {
  const state: Record<string, string> = {};
  for (const f of ALL_FIELDS) {
    const value = tier.detalhes[f.key];
    if (isListLike(f.type)) {
      state[f.key] = Array.isArray(value) ? (value as string[]).join(', ') : '';
    } else {
      state[f.key] = value != null ? String(value) : '';
    }
  }
  return state;
}

/** Toggle de chips. Guarda os valores selecionados como CSV (mesma forma que os
 * campos 'list'), preservando a ordem canônica das opções. */
function MultiSelectChips({
  options,
  value,
  onChange,
}: {
  options: { value: string; label: string }[];
  value: string;
  onChange: (csv: string) => void;
}) {
  const selected = new Set(
    value.split(',').map((x) => x.trim()).filter(Boolean),
  );
  const toggle = (val: string) => {
    const next = new Set(selected);
    if (next.has(val)) next.delete(val);
    else next.add(val);
    onChange(options.filter((o) => next.has(o.value)).map((o) => o.value).join(', '));
  };
  return (
    <div className="flex flex-wrap gap-2 pt-1">
      {options.map((o) => {
        const on = selected.has(o.value);
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={on}
            onClick={() => toggle(o.value)}
            className={
              on
                ? 'rounded-full bg-[#1b76ff] px-3 py-1 text-[12px] font-semibold text-white'
                : 'rounded-full border border-[#383838]/20 px-3 py-1 text-[12px] font-semibold text-[#383838] transition-colors hover:bg-[#383838]/10'
            }
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

function TierCard({ tier }: { tier: Tier }) {
  const update = useUpdateTier();
  const { toast } = useToast();
  const [form, setForm] = useState<Record<string, string>>(() => initialForm(tier));

  const set = (key: string, value: string) =>
    setForm((s) => ({ ...s, [key]: value }));

  const save = async () => {
    const patch: TierDetails = {};
    for (const f of ALL_FIELDS) {
      if (f.readOnly) continue; // fonte Ghost — não editável pela API
      const raw = form[f.key];
      if (isListLike(f.type)) {
        const arr = raw.split(',').map((x) => x.trim()).filter(Boolean);
        if (arr.length) patch[f.key] = arr;
      } else if (raw !== '') {
        patch[f.key] = Number(raw);
      }
    }
    try {
      await update.mutateAsync({ id: tier.id, patch });
      toast({ title: 'Plano atualizado', description: tier.tier_name_debug });
    } catch (e) {
      toast({
        title: 'Não foi possível salvar',
        description: e instanceof Error ? e.message : String(e),
        variant: 'destructive',
      });
    }
  };

  return (
    <div className="mp-card space-y-6 bg-white p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-[24px] font-bold leading-none text-[#090909]">
          {tier.tier_name_debug}
        </h2>
        <span className="rounded-full bg-[#1b76ff]/10 px-3 py-1 text-[11px] font-bold text-[#1b76ff]">
          {tier.product_id}
        </span>
      </div>

      {GROUPS.map((group) => (
        <div key={group.title} className="space-y-3">
          <h3 className="text-[12px] font-bold uppercase tracking-wide text-[#383838]/50">
            {group.title}
          </h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {group.fields.map((f) => (
              <div key={f.key} className="space-y-1.5">
                <Label
                  htmlFor={`${tier.id}-${f.key}`}
                  className="text-[13px] font-semibold text-[#383838]"
                >
                  {f.label}
                </Label>
                {f.readOnly ? (
                  <div className="flex h-10 items-center rounded-xl border border-dashed border-[#383838]/20 bg-[#383838]/[0.03] px-3 text-[14px] font-semibold text-[#383838]">
                    {form[f.key] !== '' ? `R$ ${form[f.key]}` : '—'}
                  </div>
                ) : f.type === 'multiselect' ? (
                  <MultiSelectChips
                    options={f.options ?? []}
                    value={form[f.key]}
                    onChange={(v) => set(f.key, v)}
                  />
                ) : (
                  <Input
                    id={`${tier.id}-${f.key}`}
                    type={f.type === 'number' ? 'number' : 'text'}
                    min={f.type === 'number' ? 0 : undefined}
                    step={f.step}
                    value={form[f.key]}
                    onChange={(e) => set(f.key, e.target.value)}
                    className="rounded-xl border-[#383838]/15"
                  />
                )}
                {f.hint && (
                  <p className="text-[11px] text-[#383838]/50">{f.hint}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}

      <button
        type="button"
        onClick={save}
        disabled={update.isPending}
        className="inline-flex items-center gap-2 rounded-full bg-[#1b76ff] px-6 py-2 text-[13px] font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
      >
        {update.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
        {update.isPending ? 'Salvando…' : 'Salvar alterações'}
      </button>
    </div>
  );
}

export default function AdminTiersPage() {
  const { data: tiers, isLoading, error } = useTiers();

  return (
    <AdminShell footer="green">
      <div className="flex flex-col gap-4">
        <Link
          to="/admin"
          className="inline-flex w-fit items-center gap-1.5 rounded-full border border-[#383838]/20 px-3 py-1 text-[12px] font-semibold text-[#383838] no-underline transition-colors hover:bg-[#383838]/10"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Painel administrativo
        </Link>
        <div>
          <h1 className="text-[36px] font-bold leading-none text-[#393939] md:text-[48px]">
            Gestão de Tiers
          </h1>
          <p className="mt-1 text-[18px] font-normal text-[#383838]">
            Edite os limites de cada plano. Nome e preço vêm do Ghost (sincronizados 1x/dia). As mudanças de limite valem na hora, sem redeploy.
          </p>
        </div>
      </div>

      {isLoading && (
        <div className="mp-card flex items-center gap-2 bg-white p-6 text-[#383838]/60">
          <Loader2 className="h-5 w-5 animate-spin" />
          Carregando planos…
        </div>
      )}
      {error && (
        <div className="mp-card bg-white p-6 text-destructive">
          Não foi possível carregar os planos. Recarregue a página.
        </div>
      )}

      <div className="space-y-6">
        {tiers?.map((tier) => (
          <TierCard key={tier.id} tier={tier} />
        ))}
      </div>
    </AdminShell>
  );
}
