import { type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { AdminShell } from '@/components/layout/AdminShell';
import { MetricsTabs } from './MetricsTabs';

export function MetricsLayout({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <AdminShell footer="green">
      <Link
        to="/admin"
        className="inline-flex w-fit items-center gap-1.5 rounded-full border border-[#383838]/20 px-3 py-1 text-[12px] font-semibold text-[#383838] no-underline transition-colors hover:bg-[#383838]/10"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Painel administrativo
      </Link>
      <div>
        <h1 className="text-[36px] font-bold leading-none text-[#393939] md:text-[48px]">
          {title}
        </h1>
        {subtitle && (
          <p className="mt-1 text-[18px] font-normal text-[#383838]">{subtitle}</p>
        )}
      </div>
      <MetricsTabs />
      {children}
    </AdminShell>
  );
}
