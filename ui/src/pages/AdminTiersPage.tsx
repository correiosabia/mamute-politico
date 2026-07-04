import { useState } from 'react';
import { useTiers, useUpdateTier } from '@/hooks/useTiers';
import type { Tier } from '@/api/admin';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useToast } from '@/components/ui/use-toast';

const NUM_FIELDS: {
  key: 'qtd_termos' | 'qtd_consultas_ia_mes' | 'qtd_email' | 'preco_mensal';
  label: string;
}[] = [
  { key: 'qtd_termos', label: 'Parlamentares (qtd_termos)' },
  { key: 'qtd_consultas_ia_mes', label: 'Consultas IA/mês' },
  { key: 'qtd_email', label: 'E-mails (qtd_email)' },
  { key: 'preco_mensal', label: 'Preço mensal (R$)' },
];

function TierCard({ tier }: { tier: Tier }) {
  const update = useUpdateTier();
  const { toast } = useToast();
  const [form, setForm] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      NUM_FIELDS.map((f) => [
        f.key,
        tier.detalhes[f.key] != null ? String(tier.detalhes[f.key]) : '',
      ]),
    ),
  );

  const save = async () => {
    const patch: Record<string, number> = {};
    for (const f of NUM_FIELDS) {
      if (form[f.key] !== '') patch[f.key] = Number(form[f.key]);
    }
    try {
      await update.mutateAsync({ id: tier.id, patch });
      toast({ title: 'Tier atualizado', description: tier.product_id });
    } catch (e) {
      toast({
        title: 'Erro ao salvar',
        description: String(e),
        variant: 'destructive',
      });
    }
  };

  return (
    <Card className="p-6 space-y-4">
      <div>
        <h2 className="text-lg font-semibold">{tier.tier_name_debug}</h2>
        <p className="text-sm text-muted-foreground">{tier.product_id}</p>
      </div>
      <div className="grid grid-cols-2 gap-4">
        {NUM_FIELDS.map((f) => (
          <div key={f.key} className="space-y-1">
            <Label htmlFor={`${tier.id}-${f.key}`}>{f.label}</Label>
            <Input
              id={`${tier.id}-${f.key}`}
              type="number"
              min={0}
              value={form[f.key]}
              onChange={(e) =>
                setForm((s) => ({ ...s, [f.key]: e.target.value }))
              }
            />
          </div>
        ))}
      </div>
      <Button onClick={save} disabled={update.isPending}>
        {update.isPending ? 'Salvando…' : 'Salvar'}
      </Button>
    </Card>
  );
}

export default function AdminTiersPage() {
  const { data: tiers, isLoading, error } = useTiers();

  return (
    <main className="mx-auto max-w-3xl p-8 space-y-6">
      <h1 className="text-2xl font-semibold">Gestão de Tiers</h1>
      {isLoading && <p className="text-muted-foreground">Carregando…</p>}
      {error && <p className="text-destructive">Erro ao carregar tiers.</p>}
      {tiers?.map((tier) => (
        <TierCard key={tier.id} tier={tier} />
      ))}
    </main>
  );
}
