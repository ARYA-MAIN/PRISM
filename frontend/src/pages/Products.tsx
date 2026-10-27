import React, { useMemo, useState } from 'react';
import { PageHeader } from '../components/PageHeader';
import { EmptyState } from '../components/EmptyState';
import { useApi } from '../hooks/useApi';
import { apiRequest, formatNumber } from '../lib/api';
import type { ApiPage } from '../lib/api';
import { Plus, Search, X } from 'lucide-react';

type Product = { product_id: string; sku: string; product_name: string; category: string; subcategory: string; brand: string; model: string; customer_id: string; customer_name: string; available_units: number; storage_requirement: string; weight_kg: number; fragile_flag: string };
type Customer = { customer_id: string; company_name: string };
const blankForm = { customer_id: '', sku: '', product_name: '', category: '', subcategory: 'General', brand: 'Unspecified', model: 'Unspecified', unit: 'unit', dimensions: 'Not specified', weight_kg: '0', storage_requirement: 'STANDARD', fragile_flag: 'NO' };

export const Products: React.FC = () => {
  const [q, setQ] = useState('');
  const [category, setCategory] = useState('All');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(blankForm);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const path = useMemo(() => `/products?q=${encodeURIComponent(q)}&category=${encodeURIComponent(category)}&page_size=100`, [q, category]);
  const products = useApi<ApiPage<Product>>(path);
  const customers = useApi<ApiPage<Customer>>('/customers?page_size=100');
  const categories = ['All', ...Array.from(new Set((products.data?.items ?? []).map((p) => p.category))).sort()];

  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setSaving(true); setFormError(null); setMessage(null);
    try {
      await apiRequest<Product>('/products', { method: 'POST', body: JSON.stringify({ ...form, weight_kg: Number(form.weight_kg) }) });
      setMessage('Product saved to the PRISM product catalogue.'); setForm(blankForm); setShowForm(false); products.reload();
    } catch (err) { setFormError(err instanceof Error ? err.message : 'Product could not be saved.'); }
    finally { setSaving(false); }
  };
  const change = (key: keyof typeof blankForm, value: string) => setForm((prev) => ({ ...prev, [key]: value }));

  return <div className="space-y-6">
    <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3"><PageHeader title="Warehouse Product Catalog" subtitle="Product catalogue fields and customer ownership from the imported database." /><button onClick={() => setShowForm((v) => !v)} className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-white"><Plus className="h-4 w-4" />Add Product SKU</button></div>
    {message && <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-800">{message}</div>}
    {showForm && <form onSubmit={submit} className="rounded-xl border border-border bg-card p-5 space-y-4"><div className="flex items-center justify-between"><h2 className="font-bold text-sm">Create product record</h2><button type="button" onClick={() => setShowForm(false)}><X className="h-4 w-4" /></button></div><p className="text-xs text-text-secondary">The record is stored in <code>prism_data.products</code>. Initial stock is not created by this form.</p>{formError && <p className="rounded bg-red-50 p-2 text-xs text-red-700">{formError}</p>}<div className="grid grid-cols-1 md:grid-cols-3 gap-3">{([['sku','SKU'],['product_name','Product name'],['category','Category'],['subcategory','Subcategory'],['brand','Brand'],['model','Model'],['unit','Unit'],['dimensions','Dimensions'],['weight_kg','Weight (kg)'],['storage_requirement','Storage requirement']] as [keyof typeof blankForm,string][]).map(([key,label]) => <label key={key} className="text-xs font-medium text-text-secondary">{label}<input required={['sku','product_name','category'].includes(key)} type={key === 'weight_kg' ? 'number' : 'text'} min={key === 'weight_kg' ? '0' : undefined} step={key === 'weight_kg' ? '0.001' : undefined} value={form[key]} onChange={(e) => change(key,e.target.value)} className="mt-1 w-full rounded-lg border border-border px-3 py-2 text-text-primary" /></label>)}<label className="text-xs font-medium text-text-secondary">Customer owner<select required value={form.customer_id} onChange={(e) => change('customer_id',e.target.value)} className="mt-1 w-full rounded-lg border border-border px-3 py-2 text-text-primary"><option value="">Select customer</option>{(customers.data?.items ?? []).map((x) => <option key={x.customer_id} value={x.customer_id}>{x.company_name} ({x.customer_id})</option>)}</select></label><label className="text-xs font-medium text-text-secondary">Fragile item?<select value={form.fragile_flag} onChange={(e) => change('fragile_flag',e.target.value)} className="mt-1 w-full rounded-lg border border-border px-3 py-2 text-text-primary"><option value="NO">No</option><option value="YES">Yes</option></select></label></div><div className="flex justify-end"><button disabled={saving || customers.loading} className="rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">{saving ? 'Saving…' : 'Save Product'}</button></div></form>}
    <div className="rounded-xl border border-border bg-card p-4 flex flex-col md:flex-row gap-3"><div className="relative flex-1"><Search className="absolute left-3 top-2.5 h-4 w-4 text-text-secondary" /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search SKU, product or brand" className="w-full rounded-lg border border-border py-2 pl-9 pr-3 text-xs" /></div><select value={category} onChange={(e) => setCategory(e.target.value)} className="rounded-lg border border-border px-3 py-2 text-xs">{categories.map((x) => <option key={x}>{x}</option>)}</select></div>
    {products.error && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">{products.error}</div>}
    <div className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">{products.loading && !products.data ? <div className="p-8 text-sm text-text-secondary">Loading products…</div> : products.data?.items.length ? <div className="overflow-x-auto"><table className="w-full text-left text-xs"><thead className="bg-slate-50 text-text-secondary uppercase"><tr>{['SKU','Product','Category','Brand / Model','Customer','Storage requirement','Weight','Available stock'].map((x) => <th key={x} className="px-4 py-3 font-bold whitespace-nowrap">{x}</th>)}</tr></thead><tbody className="divide-y divide-border">{products.data.items.map((p) => <tr key={p.product_id}><td className="px-4 py-3 font-mono">{p.sku}</td><td className="px-4 py-3 font-semibold">{p.product_name}</td><td className="px-4 py-3">{p.category} / {p.subcategory}</td><td className="px-4 py-3">{p.brand} {p.model}</td><td className="px-4 py-3">{p.customer_name ?? p.customer_id}</td><td className="px-4 py-3">{p.storage_requirement}{p.fragile_flag === 'YES' ? ' · Fragile' : ''}</td><td className="px-4 py-3 text-right">{formatNumber(p.weight_kg)} kg</td><td className="px-4 py-3 text-right font-bold">{formatNumber(p.available_units)}</td></tr>)}</tbody></table></div> : <div className="p-8"><EmptyState title="No products found" description="Clear the search or add a product record." /></div>}<div className="border-t border-border bg-slate-50 px-4 py-3 text-[11px] text-text-secondary">{products.data ? `${products.data.total} catalogue products` : ''} · Unit prices and supplier master records are not present in the source dataset.</div></div>
  </div>;
};
