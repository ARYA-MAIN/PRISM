import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { PageHeader } from '../components/PageHeader';
import { StatCard } from '../components/StatCard';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock,
  RefreshCw,
} from 'lucide-react';

type AreaMetric = {
  area_id: string;
  area_name: string;
  company_name: string;
  area_sqft: number;
  capacity_units: number;
  utilization_pct: number | null;
  area_status: string;
};

type OverviewResponse = {
  status: string;
  dataset: { table_count: number; total_rows: number };
  inventory: {
    available_units: number;
    reserved_units: number;
    damaged_units: number;
    quarantined_units: number;
    inventory_records: number;
    products_in_stock: number;
  };
  space_utilization: {
    warehouse_location_capacity: {
      total_capacity_units: number;
      occupied_units: number;
      total_locations: number;
      empty_locations: number;
      full_locations: number;
      utilization_pct: number | null;
      remaining_capacity_units: number;
    };
    average_recorded_area_utilization_pct: number | null;
    areas: AreaMetric[];
  };
  inbound: {
    shipments_received: number;
    expected_units: number;
    received_units: number;
    damaged_units: number;
    damage_rate_pct: number;
  };
  outbound: {
    outbound_records: number;
    dispatched_records: number;
    requested_units: number;
    picked_units: number;
    packed_units: number;
    pick_rate_pct: number;
    pack_rate_pct: number;
    avg_order_to_dispatch_hours: number | null;
  };
  orders: {
    total_orders: number;
    status_breakdown: { status: string; order_count: number }[];
  };
  delivery_status_breakdown: { delivery_status: string; record_count: number }[];
  compliance: {
    total_certificates: number;
    expired_certificates: number;
    expiring_within_30_days: number;
    failed_verification: number;
  };
  workforce: { total_workers: number; active_workers: number };
  activity: { total_activity_events: number; latest_activity_at: string | null };
};

type Alert = {
  priority: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | string;
  category: string;
  title: string;
  description: string;
  evidence: Record<string, unknown>;
  suggested_action: string;
  requires_human_review: boolean;
};

type AlertsResponse = {
  status: string;
  alert_count: number;
  priority_counts: Record<string, number>;
  rule_based: boolean;
  note: string;
  alerts: Alert[];
};

const numberFormat = new Intl.NumberFormat('en-IN');
const formatNumber = (value: number | null | undefined) =>
  value == null ? '—' : numberFormat.format(value);
const formatPercent = (value: number | null | undefined) =>
  value == null ? '—' : `${value.toFixed(2)}%`;

function priorityClass(priority: string) {
  switch (priority.toUpperCase()) {
    case 'CRITICAL': return 'bg-red-100 text-red-800 border-red-200';
    case 'HIGH': return 'bg-orange-100 text-orange-800 border-orange-200';
    case 'MEDIUM': return 'bg-amber-100 text-amber-800 border-amber-200';
    default: return 'bg-slate-100 text-slate-700 border-slate-200';
  }
}

export const Dashboard: React.FC = () => {
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [alertsData, setAlertsData] = useState<AlertsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const loadDashboard = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);

    try {
      const [overviewResponse, alertsResponse] = await Promise.all([
        fetch('/api/analytics/overview'),
        fetch('/api/analytics/alerts'),
      ]);

      if (!overviewResponse.ok) {
        throw new Error(`Analytics overview request failed (${overviewResponse.status}).`);
      }
      if (!alertsResponse.ok) {
        throw new Error(`Operational alerts request failed (${alertsResponse.status}).`);
      }

      const [overviewJson, alertsJson] = await Promise.all([
        overviewResponse.json() as Promise<OverviewResponse>,
        alertsResponse.json() as Promise<AlertsResponse>,
      ]);

      setOverview(overviewJson);
      setAlertsData(alertsJson);
      setLastUpdated(new Date());
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Could not load PRISM analytics.';
      setError(`${message} Make sure the FastAPI backend is running and the Vite API proxy is configured.`);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  const pendingOrders = useMemo(() => {
    if (!overview) return 0;
    return overview.orders.status_breakdown
      .filter((item) => ['pending', 'processing'].includes(item.status.toLowerCase()))
      .reduce((sum, item) => sum + item.order_count, 0);
  }, [overview]);

  const complianceToReview = overview
    ? overview.compliance.expired_certificates
      + overview.compliance.expiring_within_30_days
      + overview.compliance.failed_verification
    : 0;

  const topAlerts = alertsData?.alerts.slice(0, 8) ?? [];

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
        <PageHeader
          title="Warehouse Operations Overview"
          subtitle="Live operational metrics and rule-based alerts from your PRISM database."
        />
        <div className="flex flex-col items-start md:items-end gap-2">
          <div className="inline-flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-800">
            <CheckCircle2 className="h-4 w-4" />
            {overview ? 'Live API connected' : 'Connecting to API'}
          </div>
          <button
            type="button"
            onClick={() => void loadDashboard(true)}
            disabled={refreshing}
            className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-xs font-semibold text-text-primary hover:bg-slate-50 disabled:opacity-60"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            {refreshing ? 'Refreshing…' : 'Refresh data'}
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
          <div>
            <p className="font-bold">Could not load live dashboard data</p>
            <p className="mt-1">{error}</p>
            <button className="mt-2 font-bold underline" onClick={() => void loadDashboard(true)}>
              Try again
            </button>
          </div>
        </div>
      )}

      {loading && !overview ? (
        <div className="rounded-xl border border-border bg-card p-8 text-sm text-text-secondary">
          Loading live PRISM analytics…
        </div>
      ) : overview ? (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
            <StatCard
              title="Available Inventory"
              value={formatNumber(overview.inventory.available_units)}
              subtext={`${formatNumber(overview.inventory.reserved_units)} units reserved`}
              iconName="Package"
            />
            <StatCard
              title="Storage Utilization"
              value={formatPercent(overview.space_utilization.warehouse_location_capacity.utilization_pct)}
              subtext={`${formatNumber(overview.space_utilization.warehouse_location_capacity.remaining_capacity_units)} units of capacity remaining`}
              iconName="Warehouse"
            />
            <StatCard
              title="Open Orders"
              value={formatNumber(pendingOrders)}
              subtext="Pending + processing orders"
              iconName="ShoppingCart"
            />
            <StatCard
              title="Compliance Reviews"
              value={formatNumber(complianceToReview)}
              subtext="Expired, expiring soon, or failed verification"
              iconName="ShieldAlert"
            />
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
            <section className="xl:col-span-2 rounded-xl border border-border bg-card p-5 shadow-sm">
              <div className="mb-4 flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
                <div>
                  <h2 className="text-sm font-bold text-text-primary">Recorded Area Utilization</h2>
                  <p className="mt-1 text-xs text-text-secondary">Area-level utilization supplied by the dataset; storage-location utilization is shown above.</p>
                </div>
                <span className="text-xs text-text-secondary">{overview.space_utilization.areas.length} areas</span>
              </div>
              <div className="h-[280px] w-full">
                {overview.space_utilization.areas.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={overview.space_utilization.areas} margin={{ top: 8, right: 12, left: -18, bottom: 8 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                      <XAxis dataKey="company_name" tick={{ fontSize: 10 }} interval={0} angle={-10} textAnchor="end" height={55} />
                      <YAxis unit="%" tick={{ fontSize: 11 }} domain={[0, 'auto']} />
                      <Tooltip formatter={(value) => [`${Number(value ?? 0).toFixed(2)}%`, 'Recorded utilization']} />
                      <Bar dataKey="utilization_pct" name="Recorded utilization" fill="#2563EB" radius={[5, 5, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex h-full items-center justify-center text-sm text-text-secondary">No area utilization records available.</div>
                )}
              </div>
            </section>

            <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
              <h2 className="text-sm font-bold text-text-primary">Operations Snapshot</h2>
              <p className="mt-1 text-xs text-text-secondary">Aggregates from imported transaction records.</p>
              <div className="mt-5 space-y-5">
                <div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-text-secondary">Picking completion</span>
                    <strong className="text-text-primary">{formatPercent(overview.outbound.pick_rate_pct)}</strong>
                  </div>
                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
                    <div className="h-full rounded-full bg-blue-600" style={{ width: `${Math.min(100, overview.outbound.pick_rate_pct)}%` }} />
                  </div>
                  <p className="mt-1 text-[11px] text-text-secondary">{formatNumber(overview.outbound.picked_units)} of {formatNumber(overview.outbound.requested_units)} requested units picked</p>
                </div>
                <div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-text-secondary">Packing completion</span>
                    <strong className="text-text-primary">{formatPercent(overview.outbound.pack_rate_pct)}</strong>
                  </div>
                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
                    <div className="h-full rounded-full bg-indigo-500" style={{ width: `${Math.min(100, overview.outbound.pack_rate_pct)}%` }} />
                  </div>
                  <p className="mt-1 text-[11px] text-text-secondary">{formatNumber(overview.outbound.packed_units)} units packed</p>
                </div>
                <div className="grid grid-cols-2 gap-3 border-t border-border pt-4">
                  <div>
                    <p className="text-[11px] text-text-secondary">Inbound received</p>
                    <p className="mt-1 text-lg font-bold text-text-primary">{formatNumber(overview.inbound.received_units)}</p>
                    <p className="text-[10px] text-text-secondary">{formatPercent(overview.inbound.damage_rate_pct)} recorded damage rate</p>
                  </div>
                  <div>
                    <p className="text-[11px] text-text-secondary">Dispatched records</p>
                    <p className="mt-1 text-lg font-bold text-text-primary">{formatNumber(overview.outbound.dispatched_records)}</p>
                    <p className="text-[10px] text-text-secondary">of {formatNumber(overview.outbound.outbound_records)} outbound records</p>
                  </div>
                </div>
                <div className="flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-[11px] leading-relaxed text-amber-900">
                  <Clock className="mt-0.5 h-4 w-4 shrink-0" />
                  Order-to-dispatch timing needs validation before being used for decisions.
                </div>
              </div>
            </section>
          </div>

          <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
            <div className="mb-4 flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2 border-b border-border pb-3">
              <div>
                <h2 className="flex items-center gap-2 text-sm font-bold text-text-primary">
                  <Activity className="h-4 w-4 text-primary" /> Operational Alerts
                </h2>
                <p className="mt-1 text-xs text-text-secondary">Rule-based findings with evidence and suggested next actions. Human review is required.</p>
              </div>
              <div className="flex flex-wrap gap-2 text-[11px]">
                {Object.entries(alertsData?.priority_counts ?? {}).map(([priority, count]) => (
                  <span key={priority} className={`rounded-full border px-2 py-1 font-semibold ${priorityClass(priority)}`}>
                    {priority}: {count}
                  </span>
                ))}
              </div>
            </div>

            {topAlerts.length ? (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                {topAlerts.map((alert, index) => (
                  <article key={`${alert.category}-${alert.title}-${index}`} className="rounded-lg border border-border p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <span className="text-[10px] font-bold uppercase tracking-wider text-text-secondary">{alert.category}</span>
                        <h3 className="mt-1 text-sm font-bold text-text-primary">{alert.title}</h3>
                      </div>
                      <span className={`shrink-0 rounded-full border px-2 py-1 text-[10px] font-bold ${priorityClass(alert.priority)}`}>
                        {alert.priority}
                      </span>
                    </div>
                    <p className="mt-2 text-xs leading-relaxed text-text-secondary">{alert.description}</p>
                    <div className="mt-3 rounded-md bg-slate-50 p-3">
                      <p className="text-[10px] font-bold uppercase tracking-wide text-text-secondary">Suggested action</p>
                      <p className="mt-1 text-xs leading-relaxed text-text-primary">{alert.suggested_action}</p>
                    </div>
                    <p className="mt-2 text-[10px] text-text-secondary">Human review required</p>
                  </article>
                ))}
              </div>
            ) : (
              <div className="rounded-lg bg-emerald-50 p-5 text-sm text-emerald-800">No alerts were returned by the current rules.</div>
            )}
            {alertsData && alertsData.alert_count > topAlerts.length && (
              <p className="mt-3 text-xs text-text-secondary">Showing {topAlerts.length} of {alertsData.alert_count} alerts. The API returns the full list.</p>
            )}
          </section>

          <div className="flex flex-col gap-1 text-[11px] text-text-secondary sm:flex-row sm:items-center sm:justify-between">
            <span>Connected to {overview.dataset.table_count} imported tables · {formatNumber(overview.dataset.total_rows)} source rows</span>
            <span>Last refreshed: {lastUpdated ? lastUpdated.toLocaleTimeString() : '—'}</span>
          </div>
        </>
      ) : null}
    </div>
  );
};
