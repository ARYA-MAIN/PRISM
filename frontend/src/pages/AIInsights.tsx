import React from 'react';
import { useNavigate } from 'react-router-dom';
import { PageHeader } from '../components/PageHeader';
import { StatusBadge } from '../components/StatusBadge';
import { useApi } from '../hooks/useApi';
import { ArrowRight, Workflow } from 'lucide-react';

type Insight = { id: string; source: string; category: string; title: string; severity: string; description: string; evidence: Record<string, unknown>; suggested_action: string; related_recommendation_id: string | null; created_at: string | null };
type InsightsResponse = { source: string; agent_layer_connected: boolean; count: number; items: Insight[]; note: string; dataset_as_of: string };

export const AIInsights: React.FC = () => {
  const navigate = useNavigate();
  const { data, loading, error, reload } = useApi<InsightsResponse>('/insights');
  return <div className="space-y-6">
    <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3"><PageHeader title="Operational Insights" subtitle="Evidence-backed rule findings for review. The multi-agent layer is intentionally not connected yet."/><button onClick={reload} className="rounded-lg border border-border bg-card px-3 py-2 text-xs font-semibold">Refresh insights</button></div>
    <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-4 flex items-start gap-3"><Workflow className="h-5 w-5 text-indigo-700 shrink-0"/><div><p className="text-sm font-bold text-indigo-950">Rule-based mode · agent integration pending</p><p className="mt-1 text-xs leading-relaxed text-indigo-900">Current findings use deterministic rules and source evidence. This keeps the screen useful while leaving a clean result contract for your teammate's future supervisor and specialist agents.</p></div></div>
    {error && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">{error}</div>}
    {loading && !data ? <div className="rounded-xl border bg-card p-8 text-sm text-text-secondary">Evaluating operational rules…</div> : data && <>
      <div className="flex gap-3 text-xs text-text-secondary"><span>{data.count} findings</span><span>·</span><span>Dataset snapshot {data.dataset_as_of}</span></div>
      {data.items.length ? <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">{data.items.map((x)=><article key={x.id} className="rounded-xl border border-border bg-card p-5 shadow-sm"><div className="flex items-start justify-between gap-3"><div><div className="text-[10px] font-bold uppercase tracking-wider text-text-secondary">{x.category} · {x.source.replaceAll('_',' ')}</div><h2 className="mt-1 text-sm font-bold text-text-primary">{x.title}</h2></div><StatusBadge status={x.severity}/></div><p className="mt-3 text-xs leading-relaxed text-text-secondary">{x.description}</p><div className="mt-3 rounded-lg bg-slate-50 p-3"><p className="text-[10px] font-bold uppercase text-text-secondary">Suggested review</p><p className="mt-1 text-xs text-text-primary">{x.suggested_action}</p></div><details className="mt-3"><summary className="cursor-pointer text-xs font-semibold text-primary">View evidence fields</summary><pre className="mt-2 max-h-48 overflow-auto rounded-lg bg-slate-950 p-3 text-[10px] text-slate-100">{JSON.stringify(x.evidence,null,2)}</pre></details>{x.related_recommendation_id && <button onClick={()=>navigate(`/ai-insights/${x.related_recommendation_id}`)} className="mt-3 inline-flex items-center gap-1 text-xs font-bold text-primary">Open replenishment review <ArrowRight className="h-3.5 w-3.5"/></button>}</article>)}</div> : <div className="rounded-xl border border-border bg-card p-8 text-sm text-text-secondary">No findings were returned by the current rules.</div>}
      <p className="text-[11px] text-text-secondary">{data.note}</p>
    </>}
  </div>;
};
