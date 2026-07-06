import { useState } from 'react';
import { Loader2, Search } from 'lucide-react';
import { MetricsLayout } from '@/components/admin/MetricsLayout';
import { UsersTable } from '@/components/admin/UsersTable';
import { useMetricsUsers } from '@/hooks/useMetrics';

export default function AdminMetricsUsersPage() {
  const [search, setSearch] = useState('');
  const query = useMetricsUsers(search.trim() ? { search: search.trim() } : undefined);
  const users = query.data?.users ?? [];

  return (
    <MetricsLayout title="Por usuário" subtitle="Selecione um usuário para ver o detalhe.">
      <div className="mp-card flex items-center gap-2 bg-white px-4 py-3">
        <Search className="h-4 w-4 text-[#383838]/50" />
        <input
          placeholder="Filtrar por nome ou e-mail…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full bg-transparent text-[14px] text-[#090909] outline-none placeholder:text-[#383838]/40"
        />
      </div>

      {query.isLoading ? (
        <div className="mp-card flex items-center gap-2 bg-white p-6 text-[#383838]/60">
          <Loader2 className="h-5 w-5 animate-spin" />
          Carregando…
        </div>
      ) : users.length > 0 ? (
        <UsersTable users={users} rate={query.data?.usd_brl_rate} />
      ) : (
        <div className="mp-card bg-white p-6 text-[#383838]/60">
          {search.trim() ? 'Nenhum usuário encontrado.' : 'Sem usuários ainda.'}
        </div>
      )}
    </MetricsLayout>
  );
}
