import { Link } from 'react-router-dom';

export default function AdminPage() {
  return (
    <main className="mx-auto max-w-3xl p-8 space-y-4">
      <h1 className="text-2xl font-semibold">Painel administrativo</h1>
      <ul className="list-disc pl-6">
        <li>
          <Link to="/admin/tiers" className="text-primary underline">
            Gestão de Tiers
          </Link>
        </li>
      </ul>
    </main>
  );
}
