import React, { useMemo, useState } from 'react';
import { PageHeader } from '../components/PageHeader';
import { StatCard } from '../components/StatCard';
import { useApi } from '../hooks/useApi';
import { apiRequest, formatDate, formatNumber } from '../lib/api';
import type { ApiPage } from '../lib/api';
import { X } from 'lucide-react';
import { OrderOutboundWorkflow } from '../components/OrderOutboundWorkflow';

type Summary = {
  inbound: { records: number; expected_units: number; received_units: number; damaged_units: number; inspection_review_count: number };
  orders: { records: number; status_breakdown: { status: string; count: number; units: number }[] };
  outbound: { records: number; dispatched_records: number; requested_units: number; picked_units: number; packed_units: number; delivery_review_records: number };
  returns: { records: number; returned_units: number };
  movements: { records: number };
  activity: { records: number; latest_at: string | null };
  source_limitations: string[];
};
type OperationRecord = Record<string, unknown> & { id: string };
type ProductOption = { product_id: string; sku: string; product_name: string; customer_id: string; customer_name: string; storage_requirement: string; unit: string };
type LocationOption = { location_id: string; location_type: string; capacity_units: number; occupied_units: number; remaining_capacity_units: number; status: string; area_customer_id: string; area_name: string; zone_name: string; segment_name: string };
type WorkerOption = { worker_id: string; name: string; role: string; skill: string; shift: string };
type InboundOptions = { products: ProductOption[]; locations: LocationOption[]; workers: WorkerOption[] };
type ReceiptForm = {
  request_key: string; product_id: string; supplier: string; expected_qty: string; received_qty: string; damaged_qty: string;
  location_id: string; batch_no: string; serial_tracking_type: 'Batch' | 'Serial'; worker_id: string;
  inspection_status: 'Passed' | 'Pending' | 'Failed'; certification_status: 'Verified' | 'Pending';
  arrival_datetime: string; storage_override: boolean; override_reason: string;
};
type ReceiptResult = {
  message: string; inbound_id: string; product_name: string; received_qty: number; available_added: number;
  quarantined_added: number; damaged_added: number; new_location_occupied_units: number; location_capacity_units: number;
};

const tabs = [{key:'inbound',label:'Inbound'},{key:'orders',label:'Orders'},{key:'outbound',label:'Outbound'},{key:'returns',label:'Returns & Damage'},{key:'movements',label:'Movements'},{key:'activity',label:'Activity Log'}];
const columns: Record<string,string[]> = {
  inbound:['id','supplier','product_name','expected_qty','received_qty','damaged_qty','arrival_datetime','inspection_status','certification_status','assigned_location_id'],
  orders:['id','customer_name','order_date','priority','product_name','quantity','requested_dispatch_date','status'],
  outbound:['id','order_id','customer_name','product_name','requested_qty','picked_qty','packed_qty','dispatch_datetime','delivery_status'],
  returns:['id','customer_name','product_name','quantity','reason','damage_type','received_date','inspection_result','disposition','status'],
  movements:['id','product_name','from_location','to_location','quantity','movement_type','timestamp','worker_name','reason'],
  activity:['id','worker_name','action_type','entity_type','entity_id','timestamp','description'],
};
function display(value: unknown) { if (value == null || value === '') return '—'; if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}/.test(value)) return formatDate(value); return String(value); }
function newReceiptForm(): ReceiptForm {
  const localNow = new Date(Date.now() - new Date().getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
  return {request_key: crypto.randomUUID(), product_id:'', supplier:'', expected_qty:'1', received_qty:'1', damaged_qty:'0', location_id:'', batch_no:'', serial_tracking_type:'Batch', worker_id:'', inspection_status:'Pending', certification_status:'Pending', arrival_datetime:localNow, storage_override:false, override_reason:''};
}
function storageCompatible(requirement: string, locationType: string): boolean {
  const req = requirement.trim().toUpperCase(); const loc = locationType.trim().toUpperCase();
  if (req === 'SECURE_RACK') return loc === 'SECURE_RACK';
  if (req === 'INDOOR_RACK') return loc === 'RACK' || loc === 'SECURE_RACK';
  return false;
}

export const Operations: React.FC = () => {
  const [tab, setTab] = useState('inbound');
  const [q, setQ] = useState('');
  const [showReceipt, setShowReceipt] = useState(false);
  const [receiptForm, setReceiptForm] = useState<ReceiptForm>(() => newReceiptForm());
  const [receiptBusy, setReceiptBusy] = useState(false);
  const [receiptError, setReceiptError] = useState<string | null>(null);
  const [receiptMessage, setReceiptMessage] = useState<string | null>(null);
  const summary = useApi<Summary>('/operations/summary');
  const rows = useApi<ApiPage<OperationRecord>>(`/operations/${tab}?q=${encodeURIComponent(q)}&page_size=50`);
  const options = useApi<InboundOptions>('/workflows/inbound-options');
  const selectedProduct = options.data?.products.find((x) => x.product_id === receiptForm.product_id);
  const customerLocations = useMemo(() => selectedProduct ? (options.data?.locations ?? []).filter((x) => x.area_customer_id === selectedProduct.customer_id) : [], [options.data, selectedProduct]);
  const selectedLocation = customerLocations.find((x) => x.location_id === receiptForm.location_id);
  const storageMismatch = !!selectedProduct && !!selectedLocation && !storageCompatible(selectedProduct.storage_requirement, selectedLocation.location_type);
  const requestedReceiptQty = Number(receiptForm.received_qty || 0);
  const capacityExceeded = !!selectedLocation && requestedReceiptQty > selectedLocation.remaining_capacity_units;

  const changeReceipt = (key: keyof ReceiptForm, value: string | boolean) => {
    setReceiptForm((old) => ({ ...old, [key]: value } as ReceiptForm));
  };

  const submitReceipt = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setReceiptBusy(true); setReceiptError(null); setReceiptMessage(null);
    try {
      const result = await apiRequest<ReceiptResult>('/workflows/inbound-receipts', {
        method: 'POST',
        body: JSON.stringify({
          ...receiptForm,
          supplier: receiptForm.supplier.trim(),
          batch_no: receiptForm.batch_no.trim(),
          expected_qty: Number(receiptForm.expected_qty),
          received_qty: Number(receiptForm.received_qty),
          damaged_qty: Number(receiptForm.damaged_qty),
          arrival_datetime: receiptForm.arrival_datetime || null,
          override_reason: receiptForm.override_reason.trim() || null,
        }),
      });
      setReceiptMessage(`${result.message} ${result.inbound_id}: ${result.available_added} available, ${result.quarantined_added} quarantined and ${result.damaged_added} damaged units recorded.`);
      setShowReceipt(false); setReceiptForm(newReceiptForm());
      setTab('inbound'); setQ(''); rows.reload(); summary.reload(); options.reload();
    } catch (e) {
      setReceiptError(e instanceof Error ? e.message : 'Receipt could not be recorded.');
    } finally { setReceiptBusy(false); }
  };

  return <div className="space-y-6">
    <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
      <PageHeader title="Warehouse Operations" subtitle="Historical records remain intact. New inbound receipts are validated and committed as live stock operations." />
      {tab === 'inbound' && <button onClick={() => { setReceiptError(null); setReceiptMessage(null); setShowReceipt((v) => !v); }} className="shrink-0 rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-white">{showReceipt ? 'Close receipt form' : 'Record inbound receipt'}</button>}
    </div>
    {summary.error && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">{summary.error}</div>}
    {receiptMessage && <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-800">{receiptMessage}</div>}
    {receiptError && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">{receiptError}</div>}
{(tab === 'orders' || tab === 'outbound') && (
  <OrderOutboundWorkflow
    mode={tab}
    onChanged={() => {
      rows.reload();
      summary.reload();
    }}
    onReserved={() => setTab('outbound')}
  />
)}
    {showReceipt && tab === 'inbound' && <form onSubmit={submitReceipt} className="space-y-4 rounded-xl border border-border bg-card p-5">
      <div className="flex items-start justify-between gap-3"><div><h2 className="text-sm font-bold">Record an inbound receipt</h2><p className="mt-1 text-xs text-text-secondary">Saving this form adds a new inbound record and updates inventory/capacity atomically. It does not replay historical receipts.</p></div><button type="button" onClick={() => setShowReceipt(false)} aria-label="Close receipt form" className="rounded p-1 text-text-secondary hover:bg-slate-100"><X className="h-4 w-4"/></button></div>
      {options.error && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">Could not load product, location or worker options: {options.error}. <button type="button" className="underline" onClick={options.reload}>Retry</button></div>}
      {options.loading && !options.data && <p className="text-xs text-text-secondary">Loading receipt options…</p>}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <label className="text-xs font-medium text-text-secondary">Product *<select required value={receiptForm.product_id} onChange={(e) => { changeReceipt('product_id', e.target.value); changeReceipt('location_id', ''); }} className="mt-1 w-full rounded-lg border border-border px-3 py-2 text-text-primary"><option value="">Select product</option>{(options.data?.products ?? []).map((p) => <option key={p.product_id} value={p.product_id}>{p.product_name} · {p.sku} · {p.customer_name}</option>)}</select></label>
        <label className="text-xs font-medium text-text-secondary">Supplier *<input required maxLength={200} value={receiptForm.supplier} onChange={(e) => changeReceipt('supplier',e.target.value)} className="mt-1 w-full rounded-lg border border-border px-3 py-2 text-text-primary" placeholder="Supplier name"/></label>
        <label className="text-xs font-medium text-text-secondary">Batch / lot number *<input required maxLength={100} value={receiptForm.batch_no} onChange={(e) => changeReceipt('batch_no',e.target.value)} className="mt-1 w-full rounded-lg border border-border px-3 py-2 text-text-primary" placeholder="e.g. BATCH-2026-001"/></label>
        <label className="text-xs font-medium text-text-secondary">Expected quantity *<input required type="number" min="1" max="1000000" step="1" value={receiptForm.expected_qty} onChange={(e) => changeReceipt('expected_qty',e.target.value)} className="mt-1 w-full rounded-lg border border-border px-3 py-2 text-text-primary"/></label>
        <label className="text-xs font-medium text-text-secondary">Received quantity *<input required type="number" min="1" max="1000000" step="1" value={receiptForm.received_qty} onChange={(e) => changeReceipt('received_qty',e.target.value)} className="mt-1 w-full rounded-lg border border-border px-3 py-2 text-text-primary"/></label>
        <label className="text-xs font-medium text-text-secondary">Damaged quantity *<input required type="number" min="0" max={receiptForm.received_qty || 0} step="1" value={receiptForm.damaged_qty} onChange={(e) => changeReceipt('damaged_qty',e.target.value)} className="mt-1 w-full rounded-lg border border-border px-3 py-2 text-text-primary"/></label>
        <label className="text-xs font-medium text-text-secondary">Storage location *<select required value={receiptForm.location_id} onChange={(e) => changeReceipt('location_id',e.target.value)} disabled={!selectedProduct} className="mt-1 w-full rounded-lg border border-border px-3 py-2 text-text-primary"><option value="">{selectedProduct ? 'Select customer-owned location' : 'Choose a product first'}</option>{customerLocations.map((loc) => <option key={loc.location_id} value={loc.location_id} disabled={loc.remaining_capacity_units <= 0}>{loc.location_id} · {loc.location_type} · free {loc.remaining_capacity_units} · {loc.zone_name}</option>)}</select></label>
        <label className="text-xs font-medium text-text-secondary">Receiving worker *<select required value={receiptForm.worker_id} onChange={(e) => changeReceipt('worker_id',e.target.value)} className="mt-1 w-full rounded-lg border border-border px-3 py-2 text-text-primary"><option value="">Select active, present worker</option>{(options.data?.workers ?? []).map((w) => <option key={w.worker_id} value={w.worker_id}>{w.name} · {w.role}</option>)}</select></label>
        <label className="text-xs font-medium text-text-secondary">Tracking method<select value={receiptForm.serial_tracking_type} onChange={(e) => changeReceipt('serial_tracking_type',e.target.value)} className="mt-1 w-full rounded-lg border border-border px-3 py-2 text-text-primary"><option value="Batch">Batch</option><option value="Serial">Serial</option></select></label>
        <label className="text-xs font-medium text-text-secondary">Inspection result<select value={receiptForm.inspection_status} onChange={(e) => changeReceipt('inspection_status',e.target.value)} className="mt-1 w-full rounded-lg border border-border px-3 py-2 text-text-primary"><option value="Pending">Pending</option><option value="Passed">Passed</option><option value="Failed">Failed</option></select></label>
        <label className="text-xs font-medium text-text-secondary">Certification check<select value={receiptForm.certification_status} onChange={(e) => changeReceipt('certification_status',e.target.value)} className="mt-1 w-full rounded-lg border border-border px-3 py-2 text-text-primary"><option value="Pending">Pending</option><option value="Verified">Verified</option></select></label>
        <label className="text-xs font-medium text-text-secondary">Arrival date and time<input type="datetime-local" value={receiptForm.arrival_datetime} onChange={(e) => changeReceipt('arrival_datetime',e.target.value)} className="mt-1 w-full rounded-lg border border-border px-3 py-2 text-text-primary"/></label>
      </div>
      {selectedProduct && <p className="text-xs text-text-secondary">Product owner: {selectedProduct.customer_name}. Storage requirement: <strong>{selectedProduct.storage_requirement}</strong>.</p>}
      {selectedLocation && <p className="text-xs text-text-secondary">Selected location has {selectedLocation.remaining_capacity_units} remaining capacity units. This receipt will occupy {receiptForm.received_qty || 0} units.</p>}
      {capacityExceeded && <p className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">The selected location does not have enough recorded free capacity for this receipt.</p>}
      {storageMismatch && <div className="space-y-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900"><p><strong>Storage mismatch warning.</strong> The selected location type is not confirmed compatible with the product's requirement. This dataset contains unresolved storage conflicts.</p><label className="flex items-start gap-2"><input type="checkbox" checked={receiptForm.storage_override} onChange={(e) => changeReceipt('storage_override',e.target.checked)} className="mt-0.5"/><span>Record an explicit manager override for this receipt</span></label>{receiptForm.storage_override && <label className="block">Override reason *<textarea required minLength={5} maxLength={1000} value={receiptForm.override_reason} onChange={(e) => changeReceipt('override_reason',e.target.value)} className="mt-1 w-full rounded-lg border border-amber-300 bg-white px-3 py-2" placeholder="Explain why this location was approved despite the mismatch"/></label>}</div>}
      {receiptForm.inspection_status !== 'Passed' || receiptForm.certification_status !== 'Verified' ? <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">Stock that has not passed inspection and certification verification will be quarantined. Damaged units will be recorded separately and will not be available.</p> : null}
      <div className="flex justify-end gap-2"><button type="button" onClick={() => setShowReceipt(false)} className="rounded-lg border border-border px-4 py-2 text-xs font-semibold">Cancel</button><button type="submit" disabled={receiptBusy || !options.data || !receiptForm.product_id || !receiptForm.location_id || !receiptForm.worker_id || capacityExceeded || (storageMismatch && (!receiptForm.storage_override || receiptForm.override_reason.trim().length < 5))} className="rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">{receiptBusy ? 'Recording receipt…' : 'Record receipt'}</button></div>
    </form>}

    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4"><StatCard title="Inbound Received" value={formatNumber(summary.data?.inbound.received_units)} subtext={`${formatNumber(summary.data?.inbound.records)} recorded receipts`} iconName="ArrowDownLeft"/><StatCard title="Orders" value={formatNumber(summary.data?.orders.records)} subtext="Recorded customer order lines" iconName="ShoppingCart"/><StatCard title="Outbound Dispatched" value={formatNumber(summary.data?.outbound.dispatched_records)} subtext={`of ${formatNumber(summary.data?.outbound.records)} source records`} iconName="Truck"/><StatCard title="Returns / Damage" value={formatNumber(summary.data?.returns.records)} subtext={`${formatNumber(summary.data?.returns.returned_units)} units recorded`} iconName="PackageX"/></div>
    {summary.data && <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs text-amber-900"><strong>Source-data limitations.</strong><ul className="mt-1 list-disc space-y-1 pl-5">{summary.data.source_limitations.map((x)=><li key={x}>{x}</li>)}</ul></div>}
    <section className="rounded-xl border border-border bg-card overflow-hidden"><div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 border-b border-border p-4"><div className="flex flex-wrap gap-1">{tabs.map((x)=><button key={x.key} onClick={()=>setTab(x.key)} className={`rounded-lg px-3 py-2 text-xs font-semibold ${tab===x.key?'bg-primary text-white':'bg-slate-100 text-text-secondary hover:bg-slate-200'}`}>{x.label}</button>)}</div><input value={q} onChange={(e)=>setQ(e.target.value)} placeholder="Search visible records" className="rounded-lg border border-border px-3 py-2 text-xs md:w-64"/></div>
      {rows.error && <div className="m-4 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">{rows.error}</div>}
      {rows.loading && !rows.data ? <div className="p-8 text-sm text-text-secondary">Loading operations records…</div> : rows.data?.items.length ? <div className="overflow-x-auto"><table className="w-full text-left text-xs"><thead className="bg-slate-50 text-text-secondary uppercase"><tr>{(columns[tab] ?? columns.inbound).map((key)=><th key={key} className="px-4 py-3 font-bold whitespace-nowrap">{key.replaceAll('_',' ')}</th>)}</tr></thead><tbody className="divide-y divide-border">{rows.data.items.map((r)=><tr key={r.id} className="hover:bg-slate-50/60">{(columns[tab] ?? columns.inbound).map((key)=><td key={key} className="max-w-[260px] px-4 py-3">{display(r[key])}</td>)}</tr>)}</tbody></table></div> : <div className="p-8 text-sm text-text-secondary">No records match this view.</div>}
      <div className="border-t border-border bg-slate-50 px-4 py-3 text-[11px] text-text-secondary">{rows.data ? `Showing ${rows.data.items.length} of ${rows.data.total} records` : 'Source records are read-only in this view, except for supported operational forms.'}</div>
    </section>
    {summary.data && <div className="grid grid-cols-1 md:grid-cols-3 gap-4"><div className="rounded-xl border border-border bg-card p-4"><p className="text-xs text-text-secondary">Picking completion</p><p className="mt-1 text-2xl font-bold">{summary.data.outbound.requested_units ? `${(100*summary.data.outbound.picked_units/summary.data.outbound.requested_units).toFixed(1)}%` : '—'}</p><p className="text-[11px] text-text-secondary">{formatNumber(summary.data.outbound.picked_units)} of {formatNumber(summary.data.outbound.requested_units)} requested units</p></div><div className="rounded-xl border border-border bg-card p-4"><p className="text-xs text-text-secondary">Packing completion</p><p className="mt-1 text-2xl font-bold">{summary.data.outbound.requested_units ? `${(100*summary.data.outbound.packed_units/summary.data.outbound.requested_units).toFixed(1)}%` : '—'}</p><p className="text-[11px] text-text-secondary">{formatNumber(summary.data.outbound.packed_units)} packed units in source records</p></div><div className="rounded-xl border border-border bg-card p-4"><p className="text-xs text-text-secondary">Latest activity record</p><p className="mt-1 text-lg font-bold">{formatDate(summary.data.activity.latest_at)}</p><p className="text-[11px] text-text-secondary">{formatNumber(summary.data.activity.records)} total events · historical plus new activity</p></div></div>}
  </div>;
};
