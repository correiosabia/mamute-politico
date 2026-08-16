import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import {
  fetchMarcacoesConfig,
  saveMarcacoesConfig,
  type MarcacoesConfigAdmin,
} from '@/api/admin';
import { ApiError } from '@/api/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';

const ESCOPOS: Array<{ valor: 'monitorados' | 'todos'; rotulo: string }> = [
  { valor: 'monitorados', rotulo: 'Só quem o assinante monitora' },
  { valor: 'todos', rotulo: 'Qualquer parlamentar do catálogo' },
];

const MIN_MAMUTES = 1;
const MAX_MAMUTES = 5;

/**
 * nada aqui sugere o que o mamutometro significa
 */
export function MarcacoesConfigPanel() {
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: ['admin', 'marcacoes-config'],
    queryFn: fetchMarcacoesConfig,
    retry: false,
  });

  const [form, setForm] = useState<Omit<MarcacoesConfigAdmin, 'updated_at'> | null>(null);

  useEffect(() => {
    if (!data) return;
    setForm({
      mamutometro_max_level: data.mamutometro_max_level,
      mamutometro_notice_text: data.mamutometro_notice_text,
      mamutometro_escopo: data.mamutometro_escopo,
      tags_escopo: data.tags_escopo,
    });
  }, [data]);

  const mutation = useMutation({
    mutationFn: () => saveMarcacoesConfig(form!),
    onSuccess: (result) => {
      queryClient.setQueryData(['admin', 'marcacoes-config'], result);
      // A tela do assinante lê a versão resolvida; invalidar evita config velha.
      void queryClient.invalidateQueries({ queryKey: ['marcacoes-settings'] });
      toast.success('Configuração salva.');
    },
    onError: (error) => {
      toast.error(
        error instanceof ApiError || error instanceof Error
          ? error.message
          : 'Não foi possível salvar.',
      );
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-6 text-[#383838]/60">
        <Loader2 className="h-4 w-4 animate-spin" />
        <span>Carregando configuração...</span>
      </div>
    );
  }

  if (isError || !form) {
    return (
      <p className="py-4 text-sm text-destructive">
        Não foi possível carregar a configuração das marcações.
      </p>
    );
  }

  const alterar = <K extends keyof typeof form>(campo: K, valor: (typeof form)[K]) =>
    setForm({ ...form, [campo]: valor });

  return (
    <section className="space-y-5">
      <div>
        <h2 className="text-[24px] font-bold leading-none text-[#090909]">
          Marcações pessoais
        </h2>
        <p className="mt-2 text-[13px] leading-relaxed text-[#383838]/70">
          Quais planos têm mamutômetro fica no painel de funcionalidades. Quantos
          parlamentares cada plano pode marcar fica na tela de planos, no campo{' '}
          <code>qtd_mamutometro</code>.
        </p>
      </div>

      <div className="grid gap-5 md:grid-cols-2">
        <label className="block">
          <span className="text-[13px] font-semibold text-[#383838]">
            Tamanho da escala
          </span>
          <Input
            type="number"
            min={MIN_MAMUTES}
            max={MAX_MAMUTES}
            value={form.mamutometro_max_level}
            onChange={(e) =>
              alterar('mamutometro_max_level', Number(e.target.value))
            }
            className="mt-1"
          />
          <span className="mt-1 block text-[12px] text-[#383838]/60">
            De {MIN_MAMUTES} a {MAX_MAMUTES} mamutes. Reduzir não apaga marcação:
            o que passa do novo tamanho aparece no topo da escala e volta ao
            original se você aumentar de novo.
          </span>
        </label>

        <label className="block">
          <span className="text-[13px] font-semibold text-[#383838]">
            Quem pode receber mamutômetro
          </span>
          <select
            value={form.mamutometro_escopo}
            onChange={(e) =>
              alterar(
                'mamutometro_escopo',
                e.target.value as 'monitorados' | 'todos',
              )
            }
            className="mt-1 h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
          >
            {ESCOPOS.map((opcao) => (
              <option key={opcao.valor} value={opcao.valor}>
                {opcao.rotulo}
              </option>
            ))}
          </select>
        </label>

        <label className="block md:col-span-2">
          <span className="text-[13px] font-semibold text-[#383838]">
            Quem pode receber tags
          </span>
          <select
            value={form.tags_escopo}
            onChange={(e) =>
              alterar('tags_escopo', e.target.value as 'monitorados' | 'todos')
            }
            className="mt-1 h-10 w-full rounded-md border border-input bg-background px-3 text-sm md:max-w-sm"
          >
            {ESCOPOS.map((opcao) => (
              <option key={opcao.valor} value={opcao.valor}>
                {opcao.rotulo}
              </option>
            ))}
          </select>
        </label>

        <label className="block md:col-span-2">
          <span className="text-[13px] font-semibold text-[#383838]">
            Aviso de primeira utilização
          </span>
          <Textarea
            value={form.mamutometro_notice_text}
            onChange={(e) => alterar('mamutometro_notice_text', e.target.value)}
            rows={3}
            className="mt-1"
          />
          <span className="mt-1 block text-[12px] text-[#383838]/60">
            Este texto não deve dizer o que cada nível significa — quem define a
            regra é cada assinante, e é isso que mantém a marcação privada.
          </span>
        </label>
      </div>

      <Button
        onClick={() => mutation.mutate()}
        disabled={mutation.isPending}
        className="rounded-full"
      >
        {mutation.isPending ? 'Salvando...' : 'Salvar marcações'}
      </Button>
    </section>
  );
}
