import React, { useState } from 'react';
import { PageHeader } from '../components/PageHeader';
import { useApi } from '../hooks/useApi';
import { apiRequest, downloadReport, formatNumber } from '../lib/api';
import { Download, Eye, X } from 'lucide-react';

type ReportMeta = { key: string; title: string; format: string; download_endpoint: string; preview_endpoint: string };
type ReportsResponse = { items: ReportMeta[]; note: string };
type Preview = { key: string; title: string; columns: string[]; items: Record<string, unknown>[]; total: number };
export const Reports: React.FC = () => {
  const { data, loading, error } = useApi<ReportsResponse>('/reports');
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const openPreview = async (key: string) => { setBusyKey(key); setFailure(null); setMessage(null); try { setPreview(await apiRequest<Preview>(`/reports/${encodeURIComponent(key)}/preview?limit=25`)); } catch (e) { setFailure(e instanceof Error ? e.message : 'Could not preview report.'); } finally { setBusyKey(null); } };
  const download = async (item: ReportMeta) => { setBusyKey(item.key); setFailure(null); setMessage(null); try { await downloadReport(item.key,item.title); setMessage(`${item.title} CSV was generated from the current database records.`); } catch (e) { setFailure(e instanceof Error ? e.message : 'Download failed.'); } finally { setBusyKey(null); } };
  return <div className="space-y-6"><PageHeader title="Reports" subtitle="Preview and download reports generated from current PostgreSQL records."/>
    {error && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">{error}</div>}{failure && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">{failure}</div>}{message && <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-800">{message}</div>}
    <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 text-xs text-blue-900">{data?.note ?? 'Reports are generated from the current data.'} CSV is available; PDF generation is not configured.</div>
    {loading && !data ? <div className="rounded-xl border bg-card p-8 text-sm text-text-secondary">Loading report catalogue…</div> : <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">{(data?.items ?? []).map((item)=><article key={item.key} className="rounded-xl border border-border bg-card p-5 shadow-sm"><div className="text-[10px] font-bold uppercase tracking-wider text-primary">Operational report · {item.format}</div><h2 className="mt-2 text-sm font-bold">{item.title}</h2><p className="mt-1 text-xs text-text-secondary">Generated at request time from the database.</p><div className="mt-4 flex gap-2"><button disabled={busyKey!==null} onClick={()=>void openPreview(item.key)} className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-slate-50 px-3 py-2 text-xs font-semibold disabled:opacity-50"><Eye className="h-3.5 w-3.5"/>{busyKey===item.key?'Loading…':'Preview'}</button><button disabled={busyKey!==null} onClick={()=>void download(item)} className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-white px-3 py-2 text-xs font-semibold text-primary disabled:opacity-50"><Download className="h-3.5 w-3.5"/>Download CSV</button></div></article>)}</div>}
    {preview && <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4"><div className="max-h-[85vh] w-full max-w-6xl overflow-hidden rounded-xl border border-border bg-card shadow-xl"><div className="flex items-start justify-between border-b border-border p-4"><div><h2 className="text-sm font-bold">{preview.title}</h2><p className="mt-1 text-xs text-text-secondary">Previewing up to 25 rows of {formatNumber(preview.total)} total records.</p></div><button onClick={()=>setPreview(null)} aria-label="Close preview"><X className="h-4 w-4"/></button></div><div className="max-h-[65vh] overflow-auto"><table className="w-full text-left text-xs"><thead className="sticky top-0 bg-slate-50"><tr>{preview.columns.map((c)=><th key={c} className="px-3 py-2 whitespace-nowrap font-bold">{c}</th>)}</tr></thead><tbody className="divide-y divide-border">{preview.items.map((row,i)=><tr key={i}>{preview.columns.map((c)=><td key={c} className="max-w-[240px] px-3 py-2">{row[c] == null ? '—' : String(row[c])}</td>)}</tr>)}</tbody></table></div></div></div>}
  </div>;
};
