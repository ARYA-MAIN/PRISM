
import React, { useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  PackagePlus,
  RefreshCw,
} from 'lucide-react';

import { useApi } from '../hooks/useApi';
import { apiRequest, formatNumber } from '../lib/api';

type CustomerOption = {
  customer_id: string;
  company_name: string;
};

type ProductOption = {
  product_id: string;
  sku: string;
  product_name: string;
  customer_id: string;
  customer_name: string;
  storage_requirement: string;
  unit: string;
};

type LocationOption = {
  location_id: string;
  location_type: string;
  capacity_units: number;
  occupied_units: number;
  remaining_capacity_units: number;
  status: string;
  area_customer_id: string;
  area_name: string;
  zone_name: string;
  segment_name: string;
};

type WorkerOption = {
  worker_id: string;
  name: string;
  role: string;
  skill?: string;
  shift?: string;
};

type ReturnOptions = {
  customers: CustomerOption[];
  products: ProductOption[];
  locations: LocationOption[];
  workers: WorkerOption[];
};

type Disposition =
  | 'Restock'
  | 'Quarantine'
  | 'Damaged'
  | 'Dispose';

type Inspection = 'Passed' | 'Pending' | 'Failed';

type ReturnResult = {
  success: boolean;
  return_id: string;
  product_id: string;
  quantity: number;
  disposition: Disposition;
  inventory_id: string | null;
  movement_id: string | null;
  idempotent_replay: boolean;
};

type FormState = {
  request_key: string;
  customer_id: string;
  product_id: string;
  quantity: string;
  reason: string;
  damage_type: string;
  inspection_result: Inspection;
  disposition: Disposition;
  location_id: string;
  worker_id: string;
};

function newForm(): FormState {
  return {
    request_key: crypto.randomUUID(),
    customer_id: '',
    product_id: '',
    quantity: '1',
    reason: '',
    damage_type: 'None',
    inspection_result: 'Pending',
    disposition: 'Quarantine',
    location_id: '',
    worker_id: '',
  };
}

function storageCompatible(
  requirement: string,
  locationType: string
): boolean {
  const req = requirement.trim().toUpperCase();
  const loc = locationType.trim().toUpperCase();

  if (req === 'SECURE_RACK') {
    return loc === 'SECURE_RACK';
  }

  if (req === 'INDOOR_RACK') {
    return loc === 'RACK' || loc === 'SECURE_RACK';
  }

  // Unknown requirements, including FLOOR,
  // are rejected by the current backend rules.
  return false;
}

const inputClass =
  'mt-1 w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-text-primary outline-none focus:ring-2 focus:ring-primary/20';

const labelClass =
  'block text-xs font-medium text-text-secondary';

export const ReturnsDamageWorkflow: React.FC<{
  onChanged: () => void;
}> = ({ onChanged }) => {

  const options = useApi<ReturnOptions>(
    '/workflows/return-options'
  );

  const [form, setForm] = useState<FormState>(() => newForm());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<ReturnResult | null>(null);

  const update = <K extends keyof FormState>(
    key: K,
    value: FormState[K]
  ) => {
    setForm((old) => ({
      ...old,
      [key]: value,
    }));
  };

  const product = options.data?.products.find(
    (item) => item.product_id === form.product_id
  );

  const customer = options.data?.customers.find(
    (item) => item.customer_id === form.customer_id
  );

  const customerProducts = useMemo(
    () =>
      (options.data?.products ?? []).filter(
        (item) => item.customer_id === form.customer_id
      ),
    [options.data, form.customer_id]
  );

  const compatibleLocations = useMemo(
    () =>
      product
        ? (options.data?.locations ?? []).filter(
            (location) =>
              location.area_customer_id === product.customer_id &&
              storageCompatible(
                product.storage_requirement,
                location.location_type
              ) &&
              ['ACTIVE', 'AVAILABLE', 'OCCUPIED', 'PARTIAL'].includes(
                String(location.status).toUpperCase()
              )
          )
        : [],
    [options.data, product]
  );

  const selectedLocation = compatibleLocations.find(
    (item) => item.location_id === form.location_id
  );

  const quantity = Number(form.quantity || 0);

  const locationRequired = form.disposition !== 'Dispose';

  const capacityExceeded =
    !!selectedLocation &&
    quantity > selectedLocation.remaining_capacity_units;

  const invalidRestock =
    form.disposition === 'Restock' &&
    form.inspection_result !== 'Passed';

  const noCompatibleLocation =
    locationRequired &&
    !!product &&
    compatibleLocations.length === 0;

  const submit = async (
    event: React.FormEvent<HTMLFormElement>
  ) => {
    event.preventDefault();

    if (!product) {
      setError('Select a valid product.');
      return;
    }

    if (!form.customer_id || !form.worker_id) {
      setError('Select a customer and receiving worker.');
      return;
    }

    if (locationRequired && !selectedLocation) {
      setError('Select a compatible storage location.');
      return;
    }

    if (capacityExceeded) {
      setError('The selected location does not have enough capacity.');
      return;
    }

    if (invalidRestock) {
      setError('Restocking requires a Passed inspection.');
      return;
    }

    setBusy(true);
    setError(null);
    setSuccess(null);

    try {
      const result = await apiRequest<ReturnResult>(
        '/workflows/returns',
        {
          method: 'POST',
          body: JSON.stringify({
            request_key: form.request_key,
            customer_id: form.customer_id,
            product_id: form.product_id,
            quantity,
            reason: form.reason.trim(),
            damage_type: form.damage_type.trim() || 'None',
            inspection_result: form.inspection_result,
            disposition: form.disposition,
            location_id: locationRequired
              ? form.location_id
              : null,
            worker_id: form.worker_id,
          }),
        }
      );

      setSuccess(result);
      setForm(newForm());

      options.reload();
      onChanged();

    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : 'The return could not be recorded.'
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="space-y-5 rounded-xl border border-border bg-card p-5">

      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="rounded-lg bg-primary/10 p-2 text-primary">
            <PackagePlus className="h-5 w-5" />
          </div>

          <div>
            <h2 className="text-sm font-bold text-text-primary">
              Returns & Damage Processing
            </h2>

            <p className="mt-1 text-xs text-text-secondary">
              Register returned products, inspect their condition
              and determine their inventory disposition.
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={options.reload}
          disabled={options.loading}
          className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-xs font-semibold disabled:opacity-50"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh options
        </button>
      </div>

      {/* Loading */}
      {options.loading && !options.data && (
        <p className="text-xs text-text-secondary">
          Loading customers, products, locations and workers...
        </p>
      )}

      {/* Errors */}
      {options.error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
          {options.error}
          <button
            type="button"
            onClick={options.reload}
            className="ml-2 font-bold underline"
          >
            Retry
          </button>
        </div>
      )}

      {error && (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700"
        >
          {error}
        </div>
      )}

      {/* Success */}
      {success && (
        <div
          role="status"
          className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-xs text-emerald-800"
        >
          <div className="flex items-center gap-2 font-bold">
            <CheckCircle2 className="h-4 w-4" />
            Return recorded successfully
          </div>

          <div className="mt-2 space-y-1">
            <p>Return ID: {success.return_id}</p>
            <p>Quantity: {formatNumber(success.quantity)} units</p>
            <p>Disposition: {success.disposition}</p>

            {success.inventory_id && (
              <p>Inventory record: {success.inventory_id}</p>
            )}

            {success.movement_id && (
              <p>Movement record: {success.movement_id}</p>
            )}

            {success.idempotent_replay && (
              <p>This was a replay of an already completed request.</p>
            )}

            {!success.movement_id && (
              <p>No stock location or inventory movement was created for disposal.</p>
            )}
          </div>
        </div>
      )}

      {/* Return Form */}
      <form onSubmit={submit} className="space-y-5">

        <div>
          <h3 className="text-xs font-bold uppercase tracking-wide text-text-secondary">
            Return information
          </h3>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">

          {/* Customer */}
          <label className={labelClass}>
            Customer *

            <select
              required
              value={form.customer_id}
              onChange={(e) => {
                update('customer_id', e.target.value);
                update('product_id', '');
                update('location_id', '');
              }}
              className={inputClass}
            >
              <option value="">Select customer</option>

              {(options.data?.customers ?? []).map((item) => (
                <option
                  key={item.customer_id}
                  value={item.customer_id}
                >
                  {item.company_name}
                </option>
              ))}
            </select>
          </label>

          {/* Product */}
          <label className={labelClass}>
            Product / SKU *

            <select
              required
              value={form.product_id}
              disabled={!form.customer_id}
              onChange={(e) => {
                update('product_id', e.target.value);
                update('location_id', '');
              }}
              className={inputClass}
            >
              <option value="">Select product</option>

              {customerProducts.map((item) => (
                <option
                  key={item.product_id}
                  value={item.product_id}
                >
                  {item.product_name} · {item.sku}
                </option>
              ))}
            </select>
          </label>

          {/* Quantity */}
          <label className={labelClass}>
            Quantity returned *

            <input
              required
              type="number"
              min="1"
              max="1000000"
              step="1"
              value={form.quantity}
              onChange={(e) => update('quantity', e.target.value)}
              className={inputClass}
            />
          </label>

          {/* Reason */}
          <label className={labelClass}>
            Return reason *

            <input
              required
              maxLength={1000}
              value={form.reason}
              onChange={(e) => update('reason', e.target.value)}
              placeholder="Enter reason for return"
              className={inputClass}
            />
          </label>

          {/* Damage type */}
          <label className={labelClass}>
            Damage type

            <select
              value={form.damage_type}
              onChange={(e) => update('damage_type', e.target.value)}
              className={inputClass}
            >
              <option value="None">No damage reported</option>
              <option value="Physical Damage">Physical damage</option>
              <option value="Packaging Damage">Packaging damage</option>
              <option value="Electrical Damage">Electrical damage</option>
              <option value="Water Damage">Water damage</option>
              <option value="Missing Parts">Missing parts</option>
              <option value="Other">Other</option>
            </select>
          </label>

          {/* Worker */}
          <label className={labelClass}>
            Receiving worker *

            <select
              required
              value={form.worker_id}
              onChange={(e) => update('worker_id', e.target.value)}
              className={inputClass}
            >
              <option value="">Select active worker</option>

              {(options.data?.workers ?? []).map((worker) => (
                <option
                  key={worker.worker_id}
                  value={worker.worker_id}
                >
                  {worker.name} · {worker.role}
                </option>
              ))}
            </select>
          </label>

          {/* Inspection */}
          <label className={labelClass}>
            Inspection result *

            <select
              value={form.inspection_result}
              onChange={(e) =>
                update('inspection_result', e.target.value as Inspection)
              }
              className={inputClass}
            >
              <option value="Pending">Pending inspection</option>
              <option value="Passed">Passed</option>
              <option value="Failed">Failed</option>
            </select>
          </label>

          {/* Disposition */}
          <label className={labelClass}>
            Inventory disposition *

            <select
              value={form.disposition}
              onChange={(e) => {
                update('disposition', e.target.value as Disposition);
                update('location_id', '');
              }}
              className={inputClass}
            >
              <option value="Restock">Restock</option>
              <option value="Quarantine">Quarantine</option>
              <option value="Damaged">Damaged inventory</option>
              <option value="Dispose">Dispose</option>
            </select>
          </label>

          {/* Location */}
          {locationRequired && (
            <label className={labelClass}>
              Storage location *

              <select
                required
                value={form.location_id}
                onChange={(e) => update('location_id', e.target.value)}
                disabled={!product || noCompatibleLocation}
                className={inputClass}
              >
                <option value="">Select compatible location</option>

                {compatibleLocations.map((location) => (
                  <option
                    key={location.location_id}
                    value={location.location_id}
                    disabled={
                      location.remaining_capacity_units < quantity
                    }
                  >
                    {location.location_id} · {location.location_type}
                    {' · '}
                    Free: {location.remaining_capacity_units}
                  </option>
                ))}
              </select>
            </label>
          )}

        </div>

        {/* Product details */}
        {product && (
          <div className="rounded-lg bg-slate-50 p-3 text-xs text-text-secondary">
            <p>
              <strong>Customer:</strong> {customer?.company_name}
            </p>
            <p className="mt-1">
              <strong>Product:</strong> {product.product_name} ({product.sku})
            </p>
            <p className="mt-1">
              <strong>Storage requirement:</strong> {product.storage_requirement}
            </p>
          </div>
        )}

        {/* Location warnings */}
        {noCompatibleLocation && (
          <div className="flex gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <p>
              No compatible storage location is available for this
              product under the current backend storage rules.
              You may use Dispose, or select another product.
            </p>
          </div>
        )}

        {capacityExceeded && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
            The selected location does not have enough remaining
            capacity for this return.
          </div>
        )}

        {/* Business rules */}
        <div className="rounded-lg border border-border p-4 text-xs text-text-secondary space-y-2">
          <p className="font-bold text-text-primary">
            Processing rules
          </p>

          <p>
            • Restocking is allowed only after a Passed inspection.
          </p>

          <p>
            • Quarantined and damaged goods are tracked separately
            from available stock.
          </p>

          <p>
            • Disposal does not add stock or require a storage location.
          </p>

          <p>
            • New return records use the server's current date.
            Historical return records are not overwritten.
          </p>
        </div>

        {/* Actions */}
        <div className="flex flex-wrap justify-end gap-2">

          <button
            type="button"
            onClick={() => {
              setForm(newForm());
              setError(null);
              setSuccess(null);
            }}
            disabled={busy}
            className="rounded-lg border border-border px-4 py-2 text-xs font-semibold disabled:opacity-50"
          >
            Clear form
          </button>

          <button
            type="submit"
            disabled={
              busy ||
              options.loading ||
              !options.data ||
              !product ||
              !form.customer_id ||
              !form.worker_id ||
              !form.reason.trim() ||
              (locationRequired && !selectedLocation) ||
              capacityExceeded ||
              invalidRestock
            }
            className="rounded-lg bg-primary px-5 py-2 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? 'Processing return...' : 'Record return'}
          </button>

        </div>
      </form>
    </section>
  );
};
