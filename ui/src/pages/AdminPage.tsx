import { useIsAdmin } from '@/hooks/useIsAdmin';

export default function AdminPage() {
  const { isAdmin } = useIsAdmin();

  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="text-2xl font-semibold">Painel administrativo</h1>
      <p className="mt-4 text-muted-foreground">
        Acesso confirmado{isAdmin ? '' : '?'}. Painéis de gestão e métricas serão
        adicionados aqui.
      </p>
    </main>
  );
}
