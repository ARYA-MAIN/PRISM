import React, { useMemo, useState } from 'react';
import { PageHeader } from '../components/PageHeader';
import { StatCard } from '../components/StatCard';
import { StatusBadge } from '../components/StatusBadge';
import { EmptyState } from '../components/EmptyState';
import { useApi } from '../hooks/useApi';
import { formatDate, formatNumber } from '../lib/api';
import type { ApiPage } from '../lib/api';
import { RefreshCw, Search } from 'lucide-react';

type InventoryItem = {
  product_id: string; sku: string; product_name: string; category: string; brand: string;
  available_units: number; reserved_units: number; damaged_units: number; quarantined_units: number;
  location_count: number; avg_daily_demand_30d: number; planning_threshold_units: number;
  coverage_days: number | null; stock_status: string; demand_anchor_date: string | null;
};
type InventoryResponse = ApiPage<InventoryItem> & { summary: {
  product_count: number; available_units: number; low_stock_products: number; critical_products: number;
  no_recorded_demand_products: number; planning_threshold_note: string; demand_anchor_date: string | null;
} };

export const Inventory: React.FC = () => {
  const [q, setQ] = useState('');
  const [category, setCategory] = useState('All');
  const [status, setStatus] = useState('All');
  const [page, setPage] = useState(1);
  const path = useMemo(() => `/inventory?q=${encodeURIComponent(q)}&category=${encodeURIComponent(category)}&status=${encodeURIComponent(status)}&page=${page}&page_size=25`, [q, category, status, page]);
  const { data, loading, error, reload } = useApi<InventoryResponse>(path);
  const categories = ['All', ...Array.from(new Set((data?.items ?? []).map((x) => x.category))).sort()];
  const reset = () => { setQ(''); setCategory('All'); setStatus('All'); setPage(1); };

  return <div className="space-y-6">
    <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
      <PageHeader title="Inventory Intelligence" subtitle="Available, reserved, damaged and quarantined stock from the imported inventory records." />
      <button onClick={reload} className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-xs font-semibold text-text-primary"><RefreshCw className="w-3.5 h-3.5" />Refresh</button>
    </div>
    {error && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <StatCard title="Products in Catalog" value={formatNumber(data?.summary.product_count)} subtext="Products represented by imported records" iconName="Boxes" />
      <StatCard title="Available Units" value={formatNumber(data?.summary.available_units)} subtext="Excludes reserved, damaged and quarantined units" iconName="Package" />
      <StatCard title="Low / Critical SKUs" value={formatNumber((data?.summary.low_stock_products ?? 0) + (data?.summary.critical_products ?? 0))} subtext="Rule-based 7-day demand coverage check" iconName="AlertTriangle" />
    </div>
    <div className="rounded-xl border border-border bg-card p-4 flex flex-col md:flex-row gap-3">
      <div className="relative flex-1"><Search className="absolute left-3 top-2.5 h-4 w-4 text-text-secondary" /><input value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} placeholder="Search product name or SKU" className="w-full rounded-lg border border-border bg-slate-50 py-2 pl-9 pr-3 text-xs" /></div>
      <select value={category} onChange={(e) => { setCategory(e.target.value); setPage(1); }} className="rounded-lg border border-border bg-slate-50 px-3 py-2 text-xs">{categories.map((x) => <option key={x}>{x}</option>)}</select>
      <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} className="rounded-lg border border-border bg-slate-50 px-3 py-2 text-xs"><option>All</option><option>Healthy</option><option>Low Stock</option><option>Critical</option><option>No Recorded Demand</option></select>
      <button onClick={reset} className="rounded-lg border border-border bg-slate-100 px-3 py-2 text-xs font-semibold">Reset</button>
    </div>
    <div className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
      {loading && !data ? <div className="p-8 text-sm text-text-secondary">Loading inventory…</div> : data?.items.length ? <div className="overflow-x-auto"><table className="w-full text-left text-xs"><thead className="bg-slate-50 text-text-secondary uppercase"><tr>{['Product','SKU','Category','Available','Reserved','Damaged','Quarantined','7-day planning threshold','Demand/day','Coverage','Status'].map((x) => <th key={x} className="px-4 py-3 font-bold whitespace-nowrap">{x}</th>)}</tr></thead><tbody className="divide-y divide-border">{data.items.map((x) => <tr key={x.product_id} className="hover:bg-slate-50/60"><td className="px-4 py-3 font-semibold">{x.product_name}</td><td className="px-4 py-3 font-mono text-text-secondary">{x.sku}</td><td className="px-4 py-3">{x.category}</td><td className="px-4 py-3 text-right font-bold">{formatNumber(x.available_units)}</td><td className="px-4 py-3 text-right">{formatNumber(x.reserved_units)}</td><td className="px-4 py-3 text-right">{formatNumber(x.damaged_units)}</td><td className="px-4 py-3 text-right">{formatNumber(x.quarantined_units)}</td><td className="px-4 py-3 text-right">{formatNumber(x.planning_threshold_units)}</td><td className="px-4 py-3 text-right">{formatNumber(x.avg_daily_demand_30d)}</td><td className="px-4 py-3 text-right">{x.coverage_days == null ? '—' : `${x.coverage_days} days`}</td><td className="px-4 py-3"><StatusBadge status={x.stock_status} /></td></tr>)}</tbody></table></div> : <div className="p-8"><EmptyState title="No inventory rows found" description="Try clearing the filters or check whether the dataset tables have been imported." /></div>}
      <div className="flex flex-col sm:flex-row justify-between gap-2 border-t border-border bg-slate-50 px-4 py-3 text-[11px] text-text-secondary"><span>Demand anchor: {formatDate(data?.summary.demand_anchor_date)} · {data?.summary.planning_threshold_note}</span><div className="flex items-center gap-2"><span>{data ? `${data.total} products · page ${data.page}` : ''}</span><button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded border px-2 py-1 disabled:opacity-40">Previous</button><button disabled={!data || page * data.page_size >= data.total} onClick={() => setPage((p) => p + 1)} className="rounded border px-2 py-1 disabled:opacity-40">Next</button></div></div>
    </div>
  </div>;
};
