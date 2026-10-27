import React, { useState } from 'react';
import { useApi } from '../hooks/useApi';
import { apiRequest, formatDate } from '../lib/api';

type OrderOption = {
  order_id: string;
  customer_name: string;
  product_name: string;
  sku: string;
  quantity: number;
  priority: string;
  available_units: number;
  can_reserve: boolean;
  blocked_reason: string | null;
};

type WorkerOption = {
  worker_id: string;
  name: string;
  role: string;
};

type Fulfillment = {
  fulfillment_id: string;
  order_id: string;
  product_name: string;
  sku: string;
  requested_qty: number;
  status: string;
  worker_name: string;
  destination: string;
  vehicle_no: string | null;
  updated_at: string;
};

type Options = {
  orders: OrderOption[];
  workers: WorkerOption[];
  fulfillments: Fulfillment[];
};

type Result = {
  message: string;
  fulfillment_id: string;
  order_id: string;
  status: string;
};

type Props = {
  mode: 'orders' | 'outbound';
  onChanged: () => void;
  onReserved: () => void;
};

export const OrderOutboundWorkflow: React.FC<Props> = ({
  mode,
  onChanged,
  onReserved,
}) => {
  const options = useApi<Options>('/workflows/outbound-options');

  const [showForm, setShowForm] = useState(false);
  const [orderId, setOrderId] = useState('');
  const [orderSearch, setOrderSearch] = useState('');
  const [workerId, setWorkerId] = useState('');
  const [destination, setDestination] = useState('');
  const [vehicles, setVehicles] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const selectedOrder = options.data?.orders.find(
    (order) => order.order_id === orderId
  );
  const filteredOrders = (options.data?.orders ?? []).filter((order) => {
  const query = orderSearch.trim().toLowerCase();

  if (!query) return true;

  return [
    order.order_id,
    order.customer_name,
    order.product_name,
    order.sku,
  ].some((value) =>
    String(value ?? '').toLowerCase().includes(query)
  );
});

  async function reserve(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy('reserve');
    setError('');
    setMessage('');

    try {
      const result = await apiRequest<Result>(
        '/workflows/order-fulfillments/reserve',
        {
          method: 'POST',
          body: JSON.stringify({
            request_key: crypto.randomUUID(),
            order_id: orderId,
            worker_id: workerId,
            destination: destination.trim(),
          }),
        }
      );

      setMessage(`${result.message} · ${result.fulfillment_id}`);
      setShowForm(false);
      setOrderId('');
      setWorkerId('');
      setDestination('');

      options.reload();
      onChanged();
      onReserved();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Reservation failed.');
    } finally {
      setBusy(null);
    }
  }

  async function advance(
    f: Fulfillment,
    action: 'pick' | 'pack' | 'dispatch'
  ) {
    const actionKey = `${f.fulfillment_id}:${action}`;
    setBusy(actionKey);
    setError('');
    setMessage('');

    try {
      const payload: Record<string, string> = {
        request_key: crypto.randomUUID(),
      };

      if (action === 'dispatch') {
        const vehicle = (vehicles[f.fulfillment_id] ?? '').trim();

        if (!vehicle) {
          throw new Error('Enter a vehicle number first.');
        }

        payload.vehicle_no = vehicle;
      }

      const result = await apiRequest<Result>(
        `/workflows/order-fulfillments/${encodeURIComponent(f.fulfillment_id)}/${action}`,
        {
          method: 'POST',
          body: JSON.stringify(payload),
        }
      );

      setMessage(`${result.message} · ${result.fulfillment_id}`);
      options.reload();
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : `Could not ${action} order.`);
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="space-y-4 rounded-xl border border-border bg-card p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-bold">
            {mode === 'orders' ? 'Order fulfillment' : 'Live outbound workflow'}
          </h2>
          <p className="mt-1 text-xs text-text-secondary">
            Reservation → Picking → Packing → Dispatch
          </p>
        </div>

        {mode === 'orders' && (
          <button
            type="button"
            onClick={() => {
              setShowForm((value) => !value);
              setError('');
              setMessage('');
            }}
            className="rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-white"
          >
            {showForm ? 'Close form' : 'Start order fulfillment'}
          </button>
        )}

        <button
          type="button"
          disabled={options.loading}
          onClick={options.reload}
          className="rounded-lg border border-border px-3 py-2 text-xs disabled:opacity-50"
        >
          Refresh
        </button>
      </div>

      {options.loading && !options.data && (
        <p className="text-xs text-text-secondary">Loading workflow data…</p>
      )}

      {options.error && (
        <p className="rounded-lg bg-red-50 p-3 text-xs text-red-700">
          {options.error}
        </p>
      )}

      {error && (
        <p className="rounded-lg bg-red-50 p-3 text-xs text-red-700">
          {error}
        </p>
      )}

      {message && (
        <p className="rounded-lg bg-emerald-50 p-3 text-xs text-emerald-800">
          {message}
        </p>
      )}

      {mode === 'orders' && showForm && (
        <form onSubmit={reserve} className="space-y-3 rounded-lg bg-slate-50 p-4">
            <label className="block text-xs font-medium">
  Search orders
  <input
    type="search"
    value={orderSearch}
    onChange={(e) => setOrderSearch(e.target.value)}
    placeholder="Order ID, customer, product or SKU..."
    className="mt-1 w-full rounded-lg border border-border bg-white px-3 py-2"
  />
</label>
          <label className="block text-xs font-medium">
            Open order *
            <select
              required
              value={orderId}
              onChange={(e) => {
                setOrderId(e.target.value);
                const order = options.data?.orders.find(
                  (x) => x.order_id === e.target.value
                );
                setDestination(order?.customer_name ?? '');
              }}
              className="mt-1 w-full rounded-lg border border-border bg-white px-3 py-2"
            >
              <option value="">Select order</option>
              {filteredOrders.map((order) => (
                <option
                  key={order.order_id}
                  value={order.order_id}
                  disabled={!order.can_reserve}
                >
                  {order.order_id} · {order.product_name} · {order.quantity} units
                  {!order.can_reserve ? ' · Blocked' : ''}
                </option>
              ))}
            </select>
          </label>

          {selectedOrder && (
            <div className="text-xs text-text-secondary">
              {selectedOrder.customer_name} · {selectedOrder.sku} ·
              {' '}{selectedOrder.available_units} units available
              {selectedOrder.blocked_reason && (
                <p className="mt-1 text-red-600">
                  {selectedOrder.blocked_reason}
                </p>
              )}
            </div>
          )}

          <label className="block text-xs font-medium">
            Assign worker *
            <select
              required
              value={workerId}
              onChange={(e) => setWorkerId(e.target.value)}
              className="mt-1 w-full rounded-lg border border-border bg-white px-3 py-2"
            >
              <option value="">Select worker</option>
              {(options.data?.workers ?? []).map((worker) => (
                <option key={worker.worker_id} value={worker.worker_id}>
                  {worker.name} · {worker.role}
                </option>
              ))}
            </select>
          </label>

          <label className="block text-xs font-medium">
            Destination *
            <input
              required
              minLength={2}
              maxLength={200}
              value={destination}
              onChange={(e) => setDestination(e.target.value)}
              className="mt-1 w-full rounded-lg border border-border bg-white px-3 py-2"
            />
          </label>

          <button
            type="submit"
            disabled={
              busy !== null ||
              !selectedOrder?.can_reserve ||
              !workerId ||
              destination.trim().length < 2
            }
            className="rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-white disabled:opacity-50"
          >
            {busy === 'reserve' ? 'Reserving…' : 'Reserve stock'}
          </button>
        </form>
      )}

      {mode === 'orders' && (
        <p className="text-xs text-text-secondary">
          {(options.data?.orders ?? []).length} open orders available for review.
          {' '}Only eligible orders can be reserved.
        </p>
      )}

      {mode === 'outbound' && (
        <div className="space-y-3">
          {(options.data?.fulfillments ?? []).length === 0 ? (
            <p className="rounded-lg border border-dashed border-border p-6 text-center text-xs text-text-secondary">
              No live fulfillment workflows yet. Start one from the Orders tab.
            </p>
          ) : (
            options.data!.fulfillments.map((f) => (
              <div key={f.fulfillment_id} className="rounded-lg border border-border p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-bold">
                      {f.order_id} · {f.status}
                    </p>
                    <p className="mt-1 text-xs text-text-secondary">
                      {f.product_name} · {f.sku} · {f.requested_qty} units
                    </p>
                    <p className="mt-1 text-xs text-text-secondary">
                      Worker: {f.worker_name} · Destination: {f.destination}
                    </p>
                    <p className="mt-1 text-xs text-text-secondary">
                      Updated: {formatDate(f.updated_at)}
                    </p>
                  </div>

                  {f.status === 'RESERVED' && (
                    <button
                      type="button"
                      disabled={busy !== null}
                      onClick={() => advance(f, 'pick')}
                      className="rounded-lg bg-primary px-3 py-2 text-xs text-white disabled:opacity-50"
                    >
                      {busy === `${f.fulfillment_id}:pick` ? 'Picking…' : 'Mark picked'}
                    </button>
                  )}

                  {f.status === 'PICKED' && (
                    <button
                      type="button"
                      disabled={busy !== null}
                      onClick={() => advance(f, 'pack')}
                      className="rounded-lg bg-primary px-3 py-2 text-xs text-white disabled:opacity-50"
                    >
                      {busy === `${f.fulfillment_id}:pack` ? 'Packing…' : 'Mark packed'}
                    </button>
                  )}

                  {f.status === 'PACKED' && (
                    <div className="flex flex-wrap gap-2">
                      <input
                        aria-label={`Vehicle number for ${f.order_id}`}
                        value={vehicles[f.fulfillment_id] ?? ''}
                        onChange={(e) =>
                          setVehicles((old) => ({
                            ...old,
                            [f.fulfillment_id]: e.target.value,
                          }))
                        }
                        placeholder="Vehicle number"
                        className="w-36 rounded-lg border border-border px-3 py-2 text-xs"
                      />
                      <button
                        type="button"
                        disabled={busy !== null || !(vehicles[f.fulfillment_id] ?? '').trim()}
                        onClick={() => advance(f, 'dispatch')}
                        className="rounded-lg bg-primary px-3 py-2 text-xs text-white disabled:opacity-50"
                      >
                        {busy === `${f.fulfillment_id}:dispatch`
                          ? 'Dispatching…'
                          : 'Dispatch order'}
                      </button>
                    </div>
                  )}

                  {f.status === 'DISPATCHED' && (
                    <span className="text-xs font-semibold text-emerald-700">
                      Dispatch complete
                    </span>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </section>
  );
};