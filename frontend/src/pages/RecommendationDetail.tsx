import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { PageHeader } from '../components/PageHeader';
import { StatusBadge } from '../components/StatusBadge';
import { useApi } from '../hooks/useApi';
import { apiRequest, formatNumber } from '../lib/api';
import { ArrowLeft, CheckCircle2, CirclePause, XCircle } from 'lucide-react';

type Recommendation = { recommendation_id: string; product_id: string; sku: string; product_name: string; category: string; current_stock: number; avg_daily_demand_30d: number; target_14d_units: number; suggested_quantity: number; supplier_last_recorded: string | null; priority: string; stock_status: string; status: string; rationale: string; limitations: string[]; decision?: { action: string; actor_label: string; note: string | null; decided_at: string } | null };
export const RecommendationDetail: React.FC = () => {
  const { id } = useParams<{id:string}>(); const navigate = useNavigate();
  const { data, loading, error, reload } = useApi<Recommendation>(`/recommendations/${encodeURIComponent(id ?? '')}`);
  const [busy, setBusy] = useState(false); const [message, setMessage] = useState<string | null>(null); const [failure, setFailure] = useState<string | null>(null);
  const decide = async (action: 'APPROVE'|'DEFER'|'REJECT') => {
    if (!id) return; setBusy(true); setFailure(null); setMessage(null);
    try { const result = await apiRequest<{message:string}>(`/recommendations/${encodeURIComponent(id)}/decision`, {method:'POST',body:JSON.stringify({action,actor_label:'Warehouse Manager'})}); setMessage(result.message); reload(); }
    catch (e) { setFailure(e instanceof Error ? e.message : 'Decision could not be saved.'); }
    finally { setBusy(false); }
  };
  return <div className="max-w-4xl space-y-6"><button onClick={()=>navigate('/procurement')} className="inline-flex items-center gap-1 text-xs font-semibold text-text-secondary"><ArrowLeft className="h-3.5 w-3.5"/>Back to replenishment review</button>
    {loading && !data && <div className="rounded-xl border bg-card p-8 text-sm text-text-secondary">Loading recommendation evidence…</div>}
    {error && <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-xs text-red-700">{error}<button onClick={()=>navigate('/procurement')} className="ml-2 underline">Return to suggestions</button></div>}
    {message && <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-800">{message}</div>}{failure && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">{failure}</div>}
    {data && <><div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3"><PageHeader title={`Replenishment review: ${data.product_name}`} subtitle={`${data.sku} · ${data.category} · ${data.product_id}`}/><StatusBadge status={data.status}/></div>
      <div className="rounded-xl border border-border bg-card p-5"><p className="text-[10px] font-bold uppercase tracking-wider text-primary">Rule-based suggestion · human review required</p><h2 className="mt-2 text-lg font-bold">Suggested quantity: {formatNumber(data.suggested_quantity)} units</h2><p className="mt-2 text-sm text-text-secondary">{data.rationale}</p><div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3">{[['Available stock',data.current_stock],['30-day demand avg/day',data.avg_daily_demand_30d],['14-day target',data.target_14d_units],['Last recorded supplier',data.supplier_last_recorded ?? 'None recorded']].map(([label,value])=><div key={String(label)} className="rounded-lg bg-slate-50 p-3"><p className="text-[10px] text-text-secondary">{label}</p><p className="mt-1 text-sm font-bold">{typeof value==='number'?formatNumber(value):value}</p></div>)}</div></div>
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-4"><h3 className="text-xs font-bold text-amber-900">Before deciding</h3><ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-amber-900">{data.limitations.map((x)=><li key={x}>{x}</li>)}</ul><p className="mt-2 text-xs font-semibold text-amber-900">Approving this suggestion records your review decision only. It does not change stock or create a purchase order.</p></div>
      {data.decision && <div className="rounded-xl border border-border bg-card p-4 text-xs">Latest decision: <strong>{data.decision.action}</strong> by {data.decision.actor_label} at {data.decision.decided_at}{data.decision.note ? ` — ${data.decision.note}` : ''}</div>}
      <div className="flex flex-wrap gap-3"><button disabled={busy} onClick={()=>void decide('APPROVE')} className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-xs font-semibold text-white disabled:opacity-50"><CheckCircle2 className="h-4 w-4"/>Approve suggestion</button><button disabled={busy} onClick={()=>void decide('DEFER')} className="inline-flex items-center gap-2 rounded-lg border border-border bg-white px-4 py-2.5 text-xs font-semibold disabled:opacity-50"><CirclePause className="h-4 w-4"/>Defer</button><button disabled={busy} onClick={()=>void decide('REJECT')} className="inline-flex items-center gap-2 rounded-lg border border-border bg-white px-4 py-2.5 text-xs font-semibold text-danger disabled:opacity-50"><XCircle className="h-4 w-4"/>Reject</button></div>
    </>}
  </div>;
};
