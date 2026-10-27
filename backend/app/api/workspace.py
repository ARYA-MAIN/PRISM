"""PRISM non-agent workspace API.

Reads the imported prism_data snapshot and writes only user-owned app state to prism_app.
Do not import/call agent implementations here. Future insight providers should implement the
same source/evidence contract and be registered separately from these route handlers.
"""
from __future__ import annotations

import csv
import io
import json
import math
import uuid
from datetime import date, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(prefix="/api", tags=["PRISM Workspace"])

DATASET_AS_OF = "2026-09-28"
PAGE_LIMIT_DEFAULT = 50


def _all(db: Session, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return [dict(row) for row in db.execute(text(sql), params or {}).mappings().all()]


def _one(db: Session, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    row = db.execute(text(sql), params or {}).mappings().first()
    return dict(row) if row is not None else None


def _missing_data_schema_error() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail="PRISM data schema is unavailable. Confirm the prism_data schema was imported into prism_db.",
    )


def _app_schema_error() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail="PRISM app-state tables are not initialized. Run sql/001_prism_app_support.sql in prism_db using pgAdmin Query Tool.",
    )


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _status(available: int, demand_per_day: float) -> str:
    if demand_per_day <= 0:
        return "No Recorded Demand"
    coverage_days = available / demand_per_day
    if available <= 0 or coverage_days <= 3:
        return "Critical"
    if coverage_days <= 7:
        return "Low Stock"
    return "Healthy"


PRODUCT_BASE_SQL = """
WITH inv AS (
    SELECT product_id,
           COALESCE(SUM(quantity_available), 0)::bigint AS available_units,
           COALESCE(SUM(quantity_reserved), 0)::bigint AS reserved_units,
           COALESCE(SUM(quantity_damaged), 0)::bigint AS damaged_units,
           COALESCE(SUM(quantity_quarantined), 0)::bigint AS quarantined_units,
           COUNT(DISTINCT location_id)::bigint AS location_count
    FROM prism_data.inventory
    GROUP BY product_id
), anchor AS (
    SELECT COALESCE(MAX(order_date)::date, CURRENT_DATE) AS anchor_date
    FROM prism_data.orders
), demand AS (
    SELECT p.product_id,
           a.anchor_date,
           COALESCE(SUM(o.quantity) FILTER (
               WHERE o.order_date::date BETWEEN a.anchor_date - 29 AND a.anchor_date
           ), 0)::numeric / 30.0 AS avg_daily_demand_30d,
           COALESCE(SUM(o.quantity) FILTER (
               WHERE o.order_date::date BETWEEN a.anchor_date - 6 AND a.anchor_date
           ), 0)::numeric / 7.0 AS avg_daily_demand_7d,
           COALESCE(SUM(o.quantity) FILTER (
               WHERE o.order_date::date BETWEEN a.anchor_date - 59 AND a.anchor_date - 30
           ), 0)::numeric / 30.0 AS prior_avg_daily_demand_30d
    FROM prism_data.products p
    CROSS JOIN anchor a
    LEFT JOIN prism_data.orders o ON o.product_id = p.product_id
    GROUP BY p.product_id, a.anchor_date
), last_supplier AS (
    SELECT DISTINCT ON (product_id) product_id, supplier, arrival_datetime
    FROM prism_data.inbound_transactions
    ORDER BY product_id, arrival_datetime DESC, inbound_id DESC
)
SELECT p.product_id,
       p.sku,
       p.product_name,
       p.category,
       p.subcategory,
       p.brand,
       p.model,
       p.unit,
       p.dimensions,
       p.weight_kg,
       p.storage_requirement,
       p.fragile_flag,
       p.customer_id,
       c.company_name AS customer_name,
       COALESCE(i.available_units, 0)::bigint AS available_units,
       COALESCE(i.reserved_units, 0)::bigint AS reserved_units,
       COALESCE(i.damaged_units, 0)::bigint AS damaged_units,
       COALESCE(i.quarantined_units, 0)::bigint AS quarantined_units,
       COALESCE(i.location_count, 0)::bigint AS location_count,
       COALESCE(d.avg_daily_demand_30d, 0)::numeric AS avg_daily_demand_30d,
       COALESCE(d.avg_daily_demand_7d, 0)::numeric AS avg_daily_demand_7d,
       COALESCE(d.prior_avg_daily_demand_30d, 0)::numeric AS prior_avg_daily_demand_30d,
       d.anchor_date AS demand_anchor_date,
       ls.supplier AS last_recorded_supplier,
       ls.arrival_datetime AS last_inbound_at
FROM prism_data.products p
LEFT JOIN inv i ON i.product_id = p.product_id
LEFT JOIN demand d ON d.product_id = p.product_id
LEFT JOIN prism_data.customers c ON c.customer_id = p.customer_id
LEFT JOIN last_supplier ls ON ls.product_id = p.product_id
"""


def _product_rows(db: Session) -> list[dict[str, Any]]:
    try:
        records = _all(db, PRODUCT_BASE_SQL + " ORDER BY p.product_name ASC")
    except SQLAlchemyError as exc:
        raise _missing_data_schema_error() from exc
    for item in records:
        available = _int(item.get("available_units"))
        demand = _number(item.get("avg_daily_demand_30d"))
        item["current_stock"] = available
        item["avg_daily_demand"] = round(demand, 3)
        item["planning_threshold_units"] = math.ceil(demand * 7)
        item["coverage_days"] = round(available / demand, 1) if demand > 0 else None
        item["stock_status"] = _status(available, demand)
        item["trend"] = _demand_trend(_number(item.get("avg_daily_demand_7d")), demand)
    return records


def _demand_trend(recent: float, baseline: float) -> str:
    if baseline <= 0 and recent <= 0:
        return "No Recorded Demand"
    if baseline <= 0:
        return "Increasing"
    if recent > baseline * 1.10:
        return "Increasing"
    if recent < baseline * 0.90:
        return "Decreasing"
    return "Stable"


def _paged(items: list[dict[str, Any]], page: int, page_size: int) -> dict[str, Any]:
    start = (page - 1) * page_size
    return {"items": items[start:start + page_size], "total": len(items), "page": page, "page_size": page_size}


class ProductCreate(BaseModel):
    customer_id: str = Field(min_length=1, max_length=80)
    sku: str = Field(min_length=1, max_length=100)
    product_name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    subcategory: str = "General"
    brand: str = "Unspecified"
    model: str = "Unspecified"
    unit: str = "unit"
    dimensions: str = "Not specified"
    weight_kg: float = Field(default=0, ge=0, le=100000)
    storage_requirement: str = "STANDARD"
    fragile_flag: str = "NO"


class NotificationPreferences(BaseModel):
    low_stock: bool = True
    critical_stock: bool = True
    daily_digest: bool = False
    supplier_updates: bool = False


class SettingsUpdate(BaseModel):
    notifications: NotificationPreferences


class RecommendationDecision(BaseModel):
    action: Literal["APPROVE", "DEFER", "REJECT"]
    actor_label: str = Field(default="Warehouse Manager", min_length=1, max_length=120)
    note: str | None = Field(default=None, max_length=2000)


@router.get("/products")
def list_products(
    q: str | None = None,
    category: str | None = None,
    customer_id: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    items = _product_rows(db)
    needle = (q or "").strip().casefold()
    if needle:
        items = [x for x in items if needle in str(x.get("product_name", "")).casefold()
                 or needle in str(x.get("sku", "")).casefold()
                 or needle in str(x.get("brand", "")).casefold()]
    if category and category.casefold() != "all":
        items = [x for x in items if str(x.get("category", "")).casefold() == category.casefold()]
    if customer_id:
        items = [x for x in items if x.get("customer_id") == customer_id]
    return _paged(items, page, page_size)


@router.get("/products/{product_id}")
def get_product(product_id: str, db: Session = Depends(get_db)):
    item = next((x for x in _product_rows(db) if x["product_id"] == product_id or x["sku"] == product_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Product was not found.")
    return item


@router.post("/products", status_code=201)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)):
    product_id = f"PROD-{uuid.uuid4().hex[:12].upper()}"
    params = payload.model_dump()
    params["product_id"] = product_id
    try:
        customer = _one(db, "SELECT customer_id FROM prism_data.customers WHERE customer_id = :customer_id", {"customer_id": payload.customer_id})
        if not customer:
            raise HTTPException(status_code=422, detail="Choose a customer_id that exists in PRISM customers.")
        existing = _one(db, "SELECT product_id FROM prism_data.products WHERE LOWER(sku) = LOWER(:sku)", {"sku": payload.sku})
        if existing:
            raise HTTPException(status_code=409, detail="That SKU already exists.")
        db.execute(text("""
            INSERT INTO prism_data.products (
                product_id, customer_id, sku, product_name, category, subcategory, brand, model,
                unit, dimensions, weight_kg, storage_requirement, fragile_flag
            ) VALUES (
                :product_id, :customer_id, :sku, :product_name, :category, :subcategory, :brand, :model,
                :unit, :dimensions, :weight_kg, :storage_requirement, :fragile_flag
            )
        """), params)
        db.execute(text("""
            INSERT INTO prism_app.audit_events (event_type, actor_label, entity_type, entity_id, details_json)
            VALUES ('PRODUCT_CREATED', 'Warehouse Manager', 'product', :entity_id, CAST(:details AS jsonb))
        """), {
            "entity_id": product_id,
            "details": json.dumps({"sku": payload.sku, "product_name": payload.product_name, "customer_id": payload.customer_id}),
        })
        db.commit()
        return get_product(product_id, db)
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Product could not be created. Check required dataset fields and database constraints.") from exc


@router.get("/inventory")
def list_inventory(
    q: str | None = None,
    category: str | None = None,
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    all_items = _product_rows(db)
    # Summary cards describe the whole inventory, independently of list filters.
    counts = {name: sum(1 for item in all_items if item["stock_status"] == name)
              for name in ["Healthy", "Low Stock", "Critical", "No Recorded Demand"]}
    all_available_units = sum(_int(x.get("available_units")) for x in all_items)
    items = all_items
    needle = (q or "").strip().casefold()
    if needle:
        items = [x for x in items if needle in str(x.get("product_name", "")).casefold()
                 or needle in str(x.get("sku", "")).casefold()]
    if category and category.casefold() != "all":
        items = [x for x in items if str(x.get("category", "")).casefold() == category.casefold()]
    if status and status.casefold() != "all":
        items = [x for x in items if str(x.get("stock_status", "")).casefold() == status.casefold()]
    return {**_paged(items, page, page_size), "summary": {
        "product_count": len(all_items),
        "available_units": all_available_units,
        "low_stock_products": counts["Low Stock"],
        "critical_products": counts["Critical"],
        "no_recorded_demand_products": counts["No Recorded Demand"],
        "demand_anchor_date": all_items[0].get("demand_anchor_date") if all_items else None,
        "planning_threshold_note": "Planning threshold is a transparent heuristic of 7 days of recorded order demand, not a configured safety-stock value.",
    }}


@router.get("/customers")
def list_customers(
    q: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    try:
        items = _all(db, """
            SELECT c.customer_id, c.company_name, c.contact_person, c.contact_email,
                   c.contact_phone, c.allocated_area_sqft, c.contract_start, c.contract_end, c.status,
                   COUNT(DISTINCT p.product_id)::bigint AS product_count,
                   COALESCE(SUM(i.quantity_available), 0)::bigint AS available_units
            FROM prism_data.customers c
            LEFT JOIN prism_data.products p ON p.customer_id = c.customer_id
            LEFT JOIN prism_data.inventory i ON i.product_id = p.product_id
            GROUP BY c.customer_id
            ORDER BY c.company_name
        """)
    except SQLAlchemyError as exc:
        raise _missing_data_schema_error() from exc
    needle = (q or "").strip().casefold()
    if needle:
        items = [x for x in items if needle in str(x.get("company_name", "")).casefold()
                 or needle in str(x.get("customer_id", "")).casefold()]
    return _paged(items, page, page_size)


@router.get("/space/overview")
def space_overview(db: Session = Depends(get_db)):
    try:
        summary = _one(db, """
            SELECT COUNT(*)::bigint AS total_locations,
                   COALESCE(SUM(capacity_units),0)::bigint AS total_capacity_units,
                   COALESCE(SUM(occupied_units),0)::bigint AS occupied_units,
                   COUNT(*) FILTER (WHERE occupied_units = 0)::bigint AS empty_locations,
                   COUNT(*) FILTER (WHERE capacity_units > 0 AND occupied_units >= capacity_units)::bigint AS full_locations
            FROM prism_data.storage_locations
        """) or {}
        areas = _all(db, """
            SELECT a.area_id, a.area_name, a.area_sqft, a.capacity_units, a.utilization_pct, a.area_status,
                   c.company_name, c.customer_id
            FROM prism_data.areas a
            LEFT JOIN prism_data.customers c ON c.customer_id = a.customer_id
            ORDER BY a.area_name
        """)
        zones = _all(db, """
            SELECT z.zone_id, z.zone_name, z.zone_type, z.capacity_units, z.occupied_units, z.status,
                   a.area_id, a.area_name
            FROM prism_data.zones z LEFT JOIN prism_data.areas a ON a.area_id = z.area_id
            ORDER BY z.zone_name
        """)
        locations = _all(db, """
            SELECT sl.location_id, sl.rack_no, sl.shelf_no, sl.bin_no, sl.location_type,
                   sl.capacity_units, sl.occupied_units, sl.status,
                   sg.segment_id, sg.segment_name, z.zone_id, z.zone_name, a.area_id, a.area_name
            FROM prism_data.storage_locations sl
            LEFT JOIN prism_data.segments sg ON sg.segment_id = sl.segment_id
            LEFT JOIN prism_data.zones z ON z.zone_id = sg.zone_id
            LEFT JOIN prism_data.areas a ON a.area_id = z.area_id
            ORDER BY a.area_name, z.zone_name, sl.location_id
        """)
    except SQLAlchemyError as exc:
        raise _missing_data_schema_error() from exc
    capacity = _int(summary.get("total_capacity_units"))
    occupied = _int(summary.get("occupied_units"))
    summary.update({
        "remaining_capacity_units": max(0, capacity - occupied),
        "utilization_pct": round((occupied / capacity) * 100, 2) if capacity else None,
        "recorded_area_utilization_avg_pct": round(sum(_number(x.get("utilization_pct")) for x in areas) / len(areas), 2) if areas else None,
    })
    return {"summary": summary, "areas": areas, "zones": zones, "locations": locations, "dataset_as_of": DATASET_AS_OF}


@router.get("/workforce")
def list_workforce(
    q: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    try:
        items = _all(db, """
            SELECT w.worker_id, w.name, w.role, w.staff_or_trainee, w.skill,
                   w.assigned_area_id, a.area_name, w.assigned_zone_id, z.zone_name,
                   w.shift, w.joining_date, w.status, w.attendance_status
            FROM prism_data.workers w
            LEFT JOIN prism_data.areas a ON a.area_id = w.assigned_area_id
            LEFT JOIN prism_data.zones z ON z.zone_id = w.assigned_zone_id
            ORDER BY w.name
        """)
    except SQLAlchemyError as exc:
        raise _missing_data_schema_error() from exc
    all_items = items
    needle = (q or "").strip().casefold()
    if needle:
        items = [x for x in items if needle in str(x.get("name", "")).casefold()
                 or needle in str(x.get("worker_id", "")).casefold()
                 or needle in str(x.get("role", "")).casefold()]
    summary = {
        "total_workers": len(all_items),
        "active_workers": sum(1 for x in all_items if str(x.get("status", "")).casefold() == "active"),
        "present": sum(1 for x in all_items if str(x.get("attendance_status", "")).casefold() == "present"),
        "on_leave": sum(1 for x in all_items if str(x.get("attendance_status", "")).casefold() in {"leave", "on leave"}),
        "absent": sum(1 for x in all_items if str(x.get("attendance_status", "")).casefold() == "absent"),
        "productivity_metrics_available": False,
    }
    return {"summary": summary, **_paged(items, page, page_size),
            "note": "The imported dataset has worker assignments and attendance states, but no trusted shift duration or per-worker throughput measure."}


@router.get("/compliance")
def list_compliance(
    q: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    try:
        items = _all(db, """
            SELECT c.cert_id, c.owner_type, c.customer_id, cu.company_name,
                   c.product_id, p.product_name, c.certificate_type, c.certificate_no,
                   c.issuing_authority, c.issue_date, c.expiry_date, c.verification_status,
                   CURRENT_DATE AS evaluated_on,
                   (c.expiry_date < CURRENT_DATE) AS is_expired,
                   (c.expiry_date >= CURRENT_DATE AND c.expiry_date <= CURRENT_DATE + INTERVAL '30 days') AS expires_within_30_days
            FROM prism_data.certifications c
            LEFT JOIN prism_data.customers cu ON cu.customer_id = c.customer_id
            LEFT JOIN prism_data.products p ON p.product_id = c.product_id
            ORDER BY c.expiry_date ASC
        """)
    except SQLAlchemyError as exc:
        raise _missing_data_schema_error() from exc
    all_items = items
    needle = (q or "").strip().casefold()
    if needle:
        items = [x for x in items if needle in str(x.get("certificate_type", "")).casefold()
                 or needle in str(x.get("certificate_no", "")).casefold()
                 or needle in str(x.get("product_name", "")).casefold()
                 or needle in str(x.get("company_name", "")).casefold()]
    summary = {
        "total_certificates": len(all_items),
        "expired": sum(1 for x in all_items if x.get("is_expired")),
        "expiring_within_30_days": sum(1 for x in all_items if x.get("expires_within_30_days")),
        "failed_verification": sum(1 for x in all_items if str(x.get("verification_status", "")).casefold() in {"failed", "rejected", "invalid"}),
    }
    return {"summary": summary, **_paged(items, page, page_size), "dataset_as_of": DATASET_AS_OF,
            "note": "Expiry flags are evaluated against the database server's current date; source records are a static snapshot."}


OPERATIONS_QUERIES: dict[str, tuple[str, str]] = {
    "inbound": ("""
        SELECT i.inbound_id AS id, i.customer_id, c.company_name AS customer_name, i.supplier,
               i.product_id, p.product_name, i.expected_qty, i.received_qty, i.damaged_qty,
               i.arrival_datetime, i.inspection_status, i.certification_status, i.assigned_location_id
        FROM prism_data.inbound_transactions i
        LEFT JOIN prism_data.customers c ON c.customer_id = i.customer_id
        LEFT JOIN prism_data.products p ON p.product_id = i.product_id
        ORDER BY i.arrival_datetime DESC, i.inbound_id
    """, "Inbound transactions"),
    "orders": ("""
        SELECT o.order_id AS id, o.customer_id, c.company_name AS customer_name, o.order_date,
               o.priority, o.product_id, p.product_name, o.quantity, o.requested_dispatch_date, o.status
        FROM prism_data.orders o
        LEFT JOIN prism_data.customers c ON c.customer_id = o.customer_id
        LEFT JOIN prism_data.products p ON p.product_id = o.product_id
        ORDER BY o.order_date DESC, o.order_id
    """, "Customer orders"),
    "outbound": ("""
        SELECT ob.outbound_id AS id, ob.customer_id, c.company_name AS customer_name, ob.order_id,
               ob.product_id, p.product_name, ob.requested_qty, ob.picked_qty, ob.packed_qty,
               ob.dispatch_datetime, ob.destination, ob.vehicle_no, ob.delivery_status
        FROM prism_data.outbound_transactions ob
        LEFT JOIN prism_data.customers c ON c.customer_id = ob.customer_id
        LEFT JOIN prism_data.products p ON p.product_id = ob.product_id
        ORDER BY ob.dispatch_datetime DESC NULLS LAST, ob.outbound_id
    """, "Outbound transactions"),
    "returns": ("""
        SELECT r.return_id AS id, r.customer_id, c.company_name AS customer_name, r.product_id,
               p.product_name, r.quantity, r.reason, r.damage_type, r.received_date,
               r.inspection_result, r.disposition, r.status
        FROM prism_data.returns_damage r
        LEFT JOIN prism_data.customers c ON c.customer_id = r.customer_id
        LEFT JOIN prism_data.products p ON p.product_id = r.product_id
        ORDER BY r.received_date DESC, r.return_id
    """, "Returns and damage"),
    "movements": ("""
        SELECT m.movement_id AS id, m.product_id, p.product_name, m.from_location, src.status AS from_location_status,
               m.to_location, dst.status AS to_location_status, m.quantity, m.movement_type, m.timestamp,
               m.worker_id, w.name AS worker_name, m.reason
        FROM prism_data.movements m
        LEFT JOIN prism_data.products p ON p.product_id = m.product_id
        LEFT JOIN prism_data.storage_locations src ON src.location_id = m.from_location
        LEFT JOIN prism_data.storage_locations dst ON dst.location_id = m.to_location
        LEFT JOIN prism_data.workers w ON w.worker_id = m.worker_id
        ORDER BY m.timestamp DESC, m.movement_id
    """, "Stock movements"),
    "activity": ("""
        SELECT a.activity_id AS id, a.worker_id, w.name AS worker_name, a.action_type,
               a.entity_type, a.entity_id, a.timestamp, a.description
        FROM prism_data.activity_log a
        LEFT JOIN prism_data.workers w ON w.worker_id = a.worker_id
        ORDER BY a.timestamp DESC, a.activity_id
    """, "Recorded activity"),
}


@router.get("/operations/summary")
def operations_summary(db: Session = Depends(get_db)):
    try:
        inbound = _one(db, """
            SELECT COUNT(*)::bigint AS records,
                   COALESCE(SUM(expected_qty),0)::bigint AS expected_units,
                   COALESCE(SUM(received_qty),0)::bigint AS received_units,
                   COALESCE(SUM(damaged_qty),0)::bigint AS damaged_units,
                   COUNT(*) FILTER (WHERE LOWER(inspection_status) NOT IN ('passed','pass','complete','completed','approved'))::bigint AS inspection_review_count
            FROM prism_data.inbound_transactions
        """) or {}
        orders = _all(db, "SELECT status, COUNT(*)::bigint AS count, COALESCE(SUM(quantity),0)::bigint AS units FROM prism_data.orders GROUP BY status ORDER BY status")
        outbound = _one(db, """
            SELECT COUNT(*)::bigint AS records,
                   COUNT(*) FILTER (WHERE dispatch_datetime IS NOT NULL)::bigint AS dispatched_records,
                   COALESCE(SUM(requested_qty),0)::bigint AS requested_units,
                   COALESCE(SUM(picked_qty),0)::bigint AS picked_units,
                   COALESCE(SUM(packed_qty),0)::bigint AS packed_units,
                   COUNT(*) FILTER (WHERE LOWER(delivery_status) LIKE '%delay%' OR LOWER(delivery_status) LIKE '%review%')::bigint AS delivery_review_records
            FROM prism_data.outbound_transactions
        """) or {}
        returns = _one(db, "SELECT COUNT(*)::bigint AS records, COALESCE(SUM(quantity),0)::bigint AS returned_units FROM prism_data.returns_damage") or {}
        movements = _one(db, "SELECT COUNT(*)::bigint AS records FROM prism_data.movements") or {}
        activity = _one(db, "SELECT COUNT(*)::bigint AS records, MAX(timestamp) AS latest_at FROM prism_data.activity_log") or {}
    except SQLAlchemyError as exc:
        raise _missing_data_schema_error() from exc
    return {
        "inbound": inbound,
        "orders": {"records": sum(_int(x["count"]) for x in orders), "status_breakdown": orders},
        "outbound": outbound,
        "returns": returns,
        "movements": movements,
        "activity": activity,
        "source_limitations": [
            "Outbound-to-order customer/product/quantity linkage has known reconciliation issues; displayed records preserve source values.",
            "No labor duration or individual productivity measures are provided.",
            "These are historical snapshot totals, not a live scanner/IoT feed."
        ],
        "dataset_as_of": DATASET_AS_OF,
    }


@router.get("/operations/{resource}")
def list_operations_resource(
    resource: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    q: str | None = None,
    db: Session = Depends(get_db),
):
    if resource not in OPERATIONS_QUERIES:
        raise HTTPException(status_code=404, detail=f"Unsupported operations resource '{resource}'.")
    sql, label = OPERATIONS_QUERIES[resource]
    try:
        items = _all(db, sql)
    except SQLAlchemyError as exc:
        raise _missing_data_schema_error() from exc
    needle = (q or "").strip().casefold()
    if needle:
        items = [row for row in items if any(needle in str(value).casefold() for value in row.values() if value is not None)]
    return {"resource": resource, "label": label, **_paged(items, page, page_size),
            "source_note": "Values are from imported operational records; no missing fields are synthesized."}


@router.get("/forecasting")
def get_forecasting(db: Session = Depends(get_db)):
    try:
        rows = _product_rows(db)
        series = _all(db, """
            WITH anchor AS (SELECT COALESCE(MAX(order_date)::date, CURRENT_DATE) AS d FROM prism_data.orders)
            SELECT o.order_date::date AS date, COALESCE(SUM(o.quantity),0)::bigint AS units,
                   COUNT(*)::bigint AS order_lines
            FROM prism_data.orders o CROSS JOIN anchor a
            WHERE o.order_date::date BETWEEN a.d - 59 AND a.d
            GROUP BY o.order_date::date
            ORDER BY o.order_date::date
        """)
    except SQLAlchemyError as exc:
        raise _missing_data_schema_error() from exc
    forecasts: list[dict[str, Any]] = []
    for item in rows:
        avg30 = _number(item.get("avg_daily_demand_30d"))
        avg7 = _number(item.get("avg_daily_demand_7d"))
        prior30 = _number(item.get("prior_avg_daily_demand_30d"))
        forecasts.append({
            "product_id": item["product_id"], "sku": item["sku"],
            "product_name": item["product_name"], "category": item["category"],
            "avg_daily_demand_7d": round(avg7, 3),
            "baseline_daily_demand_30d": round(avg30, 3),
            "baseline_next_30d_units": round(avg30 * 30, 1),
            "prior_30d_daily_demand": round(prior30, 3),
            "trend": _demand_trend(avg7, avg30),
            "data_points_60d": len(series),
        })
    recent_total = sum(_int(x.get("units")) for x in series if x.get("date") is not None)
    return {
        "model": {
            "name": "Historical demand baseline",
            "version": "baseline-v1",
            "method": "Observed order-quantity average; 7-day recent demand compared with 30-day baseline",
            "forecast_horizon_days": 30,
            "evaluated": False,
            "accuracy_pct": None,
            "confidence_pct": None,
            "forecast_generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "demand_anchor_date": rows[0].get("demand_anchor_date") if rows else None,
            "limitations": [
                "This is a transparent baseline, not a trained ML/SARIMA model.",
                "Accuracy and confidence are not reported because holdout evaluation has not been performed.",
                "External market, seasonality and promotion data are not present in the imported dataset."
            ],
        },
        "summary": {
            "products_in_catalog": len(rows),
            "products_with_recorded_demand": sum(1 for x in forecasts if x["baseline_daily_demand_30d"] > 0),
            "observed_units_in_returned_daily_series": recent_total,
            "baseline_next_30d_units_all_products": round(sum(x["baseline_next_30d_units"] for x in forecasts), 1),
        },
        "daily_series": series,
        "forecasts": forecasts,
        "dataset_as_of": DATASET_AS_OF,
    }


def _supplier_metrics(db: Session) -> list[dict[str, Any]]:
    return _all(db, """
        SELECT supplier,
               COUNT(*)::bigint AS inbound_records,
               COALESCE(SUM(expected_qty),0)::bigint AS expected_units,
               COALESCE(SUM(received_qty),0)::bigint AS received_units,
               COALESCE(SUM(damaged_qty),0)::bigint AS damaged_units,
               CASE WHEN SUM(expected_qty) > 0 THEN ROUND(100.0 * SUM(received_qty) / SUM(expected_qty), 2) ELSE NULL END AS received_vs_expected_pct,
               CASE WHEN SUM(received_qty) > 0 THEN ROUND(100.0 * SUM(damaged_qty) / SUM(received_qty), 2) ELSE NULL END AS damage_rate_pct,
               MAX(arrival_datetime) AS last_recorded_arrival
        FROM prism_data.inbound_transactions
        GROUP BY supplier
        ORDER BY supplier
    """)


@router.get("/procurement")
def procurement_overview(db: Session = Depends(get_db)):
    products = _product_rows(db)
    suggestions: list[dict[str, Any]] = []
    for item in products:
        demand = _number(item.get("avg_daily_demand_30d"))
        available = _int(item.get("available_units"))
        target = math.ceil(demand * 14)
        quantity = max(0, target - available)
        if demand > 0 and quantity > 0:
            suggestions.append({
                "recommendation_id": f"reorder_{item['product_id']}",
                "product_id": item["product_id"], "sku": item["sku"], "product_name": item["product_name"],
                "category": item["category"], "current_stock": available,
                "avg_daily_demand_30d": round(demand, 3),
                "target_14d_units": target,
                "suggested_quantity": quantity,
                "supplier_last_recorded": item.get("last_recorded_supplier"),
                "estimated_unit_cost": None, "estimated_total_cost": None,
                "priority": "CRITICAL" if item["stock_status"] == "Critical" else "HIGH" if item["stock_status"] == "Low Stock" else "MEDIUM",
                "stock_status": item["stock_status"],
                "source": "RULE_BASED_BASELINE",
                "status": "PENDING_REVIEW",
                "rationale": f"Available stock is {available} units; the 14-day demand baseline is {target} units, based on recorded orders.",
                "limitations": ["14-day target is a planning heuristic, not an approved safety-stock policy.", "Dataset has no reliable item prices, so cost is unavailable.", "Supplier shown is the most recently recorded supplier for this product, not a ranked recommendation."],
            })
    try:
        supplier_rows = _supplier_metrics(db)
    except SQLAlchemyError as exc:
        raise _missing_data_schema_error() from exc
    try:
        latest = _all(db, """
            SELECT DISTINCT ON (recommendation_key) recommendation_key, action, actor_label, note, decided_at
            FROM prism_app.recommendation_decisions
            ORDER BY recommendation_key, decided_at DESC
        """)
    except SQLAlchemyError:
        # Current baseline suggestions remain available before app-state migration; no false
        # persistence is claimed. Write/decision endpoints still require the migration.
        db.rollback()
        latest = []
    decisions = {row["recommendation_key"]: row for row in latest}
    for item in suggestions:
        decision = decisions.get(item["recommendation_id"])
        if decision:
            item["decision"] = decision
            item["status"] = {"APPROVE": "APPROVED_FOR_REVIEW", "DEFER": "DEFERRED", "REJECT": "REJECTED"}.get(decision["action"], decision["action"])
        else:
            item["decision"] = None
    return {
        "summary": {
            "suggestion_count": len(suggestions),
            "products_needing_replenishment_review": len(suggestions),
            "pricing_data_available": False,
            "supplier_record_count": len(supplier_rows),
        },
        "suggestions": sorted(suggestions, key=lambda x: ({"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}[x["priority"]], x["product_name"])),
        "suppliers": supplier_rows,
        "method": "Rules-based replenishment baseline (14-day demand target). No autonomous purchase orders are created.",
        "dataset_as_of": DATASET_AS_OF,
    }


@router.get("/recommendations")
def list_recommendations(db: Session = Depends(get_db)):
    return procurement_overview(db)


@router.get("/recommendations/{recommendation_id}")
def get_recommendation(recommendation_id: str, db: Session = Depends(get_db)):
    data = procurement_overview(db)
    item = next((x for x in data["suggestions"] if x["recommendation_id"] == recommendation_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="No current rule-based recommendation matches that ID.")
    return item


@router.post("/recommendations/{recommendation_id}/decision")
def decide_recommendation(recommendation_id: str, payload: RecommendationDecision, db: Session = Depends(get_db)):
    recommendation = get_recommendation(recommendation_id, db)
    snapshot = json.dumps(recommendation, default=str)
    try:
        db.execute(text("""
            INSERT INTO prism_app.recommendation_decisions
                (recommendation_key, action, actor_label, note, snapshot_json)
            VALUES (:key, :action, :actor, :note, CAST(:snapshot AS jsonb))
        """), {"key": recommendation_id, "action": payload.action, "actor": payload.actor_label,
               "note": payload.note, "snapshot": snapshot})
        db.execute(text("""
            INSERT INTO prism_app.audit_events (event_type, actor_label, entity_type, entity_id, details_json)
            VALUES ('RECOMMENDATION_DECISION', :actor, 'recommendation', :entity_id, CAST(:details AS jsonb))
        """), {"actor": payload.actor_label, "entity_id": recommendation_id,
               "details": json.dumps({"action": payload.action, "note": payload.note})})
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise _app_schema_error() from exc
    return {"ok": True, "recommendation_id": recommendation_id, "action": payload.action,
            "message": "Decision saved. This records a human review decision only; it does not change stock or create a purchase order."}


@router.get("/insights")
def get_rule_based_insights(db: Session = Depends(get_db)):
    products = _product_rows(db)
    items: list[dict[str, Any]] = []
    for product in products:
        if product["stock_status"] in {"Critical", "Low Stock"}:
            items.append({
                "id": f"stock_{product['product_id']}", "source": "RULE_BASED", "category": "Inventory",
                "title": f"{product['stock_status']} stock: {product['product_name']}",
                "severity": "CRITICAL" if product["stock_status"] == "Critical" else "HIGH",
                "description": f"Available stock is {product['available_units']} units; recorded 30-day demand averages {product['avg_daily_demand_30d']} units/day.",
                "evidence": {"product_id": product["product_id"], "sku": product["sku"], "available_units": product["available_units"], "coverage_days": product["coverage_days"], "planning_threshold_units": product["planning_threshold_units"]},
                "suggested_action": "Review stock, open orders, and incoming receipts before making a replenishment decision.",
                "related_recommendation_id": f"reorder_{product['product_id']}" if product["avg_daily_demand_30d"] else None,
                "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            })
    try:
        delayed = _all(db, """
            SELECT outbound_id, delivery_status, product_id, requested_qty, picked_qty, packed_qty
            FROM prism_data.outbound_transactions
            WHERE LOWER(delivery_status) LIKE '%delay%' OR LOWER(delivery_status) LIKE '%review%'
            ORDER BY outbound_id LIMIT 100
        """)
        compliance = _all(db, """
            SELECT cert_id, certificate_type, certificate_no, expiry_date, verification_status, product_id, customer_id
            FROM prism_data.certifications
            WHERE expiry_date < CURRENT_DATE
               OR expiry_date <= CURRENT_DATE + INTERVAL '30 days'
               OR LOWER(verification_status) IN ('failed','rejected','invalid')
            ORDER BY expiry_date LIMIT 100
        """)
    except SQLAlchemyError as exc:
        raise _missing_data_schema_error() from exc
    for row in delayed:
        items.append({"id": f"delivery_{row['outbound_id']}", "source": "RULE_BASED", "category": "Outbound",
                      "title": f"Delivery exception: {row['outbound_id']}", "severity": "HIGH",
                      "description": f"Recorded delivery status is {row['delivery_status']}.", "evidence": row,
                      "suggested_action": "Inspect the source outbound record and reconcile its order/customer/product linkage before action.",
                      "related_recommendation_id": None, "created_at": None})
    for row in compliance:
        items.append({"id": f"cert_{row['cert_id']}", "source": "RULE_BASED", "category": "Compliance",
                      "title": f"Certificate review: {row['certificate_no']}",
                      "severity": "HIGH" if row.get("expiry_date") and row["expiry_date"] < date.today() else "MEDIUM",
                      "description": f"{row['certificate_type']} expires on {row['expiry_date']}; verification status: {row['verification_status']}.",
                      "evidence": row, "suggested_action": "Verify the certificate with the issuing authority and update the compliance record through an approved workflow.",
                      "related_recommendation_id": None, "created_at": None})
    items.sort(key=lambda x: ({"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(x["severity"], 4), x["title"]))
    return {"source": "RULE_BASED", "agent_layer_connected": False, "count": len(items), "items": items,
            "note": "These are transparent rule-based findings from imported records, not LLM/agent output. Review evidence before acting.",
            "dataset_as_of": DATASET_AS_OF}


DEFAULT_NOTIFICATIONS = {"low_stock": True, "critical_stock": True, "daily_digest": False, "supplier_updates": False}


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    try:
        stored = _one(db, "SELECT value_json FROM prism_app.app_settings WHERE setting_key = 'notifications'")
        warehouse = _one(db, """
            SELECT warehouse_id, name, address, total_area_sqft, total_capacity_units,
                   operating_hours, ownership_type, status
            FROM prism_data.warehouses ORDER BY warehouse_id LIMIT 1
        """)
    except SQLAlchemyError as exc:
        message = str(getattr(exc, "orig", exc)).casefold()
        if "prism_app" in message or "app_settings" in message or "does not exist" in message:
            db.rollback()
            stored = None
            try:
                warehouse = _one(db, "SELECT warehouse_id, name, address, total_area_sqft, total_capacity_units, operating_hours, ownership_type, status FROM prism_data.warehouses ORDER BY warehouse_id LIMIT 1")
            except SQLAlchemyError as inner:
                db.rollback()
                raise _missing_data_schema_error() from inner
        else:
            db.rollback()
            raise _missing_data_schema_error() from exc
    notifications = stored.get("value_json") if stored else DEFAULT_NOTIFICATIONS
    return {"profile": {"display_name": "Local Demo User", "role": "Warehouse Manager", "authentication_configured": False},
            "warehouse": warehouse, "notifications": notifications,
            "system": {"app_name": "PRISM", "api_version": "0.2.0", "dataset_as_of": DATASET_AS_OF,
                       "agent_layer_connected": False, "database_schema": "prism_data", "app_state_schema": "prism_app"}}


@router.put("/settings")
def update_settings(payload: SettingsUpdate, db: Session = Depends(get_db)):
    value = payload.notifications.model_dump()
    try:
        db.execute(text("""
            INSERT INTO prism_app.app_settings (setting_key, value_json, updated_at)
            VALUES ('notifications', CAST(:value AS jsonb), CURRENT_TIMESTAMP)
            ON CONFLICT (setting_key) DO UPDATE
            SET value_json = EXCLUDED.value_json, updated_at = CURRENT_TIMESTAMP
        """), {"value": json.dumps(value)})
        db.execute(text("""
            INSERT INTO prism_app.audit_events (event_type, actor_label, entity_type, entity_id, details_json)
            VALUES ('SETTINGS_UPDATED', 'Warehouse Manager', 'settings', 'notifications', CAST(:details AS jsonb))
        """), {"details": json.dumps(value)})
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise _app_schema_error() from exc
    return {"ok": True, "notifications": value, "message": "Notification preferences saved."}


REPORTS: dict[str, tuple[str, str]] = {
    "inventory": ("Inventory snapshot", """
        SELECT p.product_id, p.sku, p.product_name, p.category, p.brand, p.customer_id,
               COALESCE(SUM(i.quantity_available),0)::bigint AS quantity_available,
               COALESCE(SUM(i.quantity_reserved),0)::bigint AS quantity_reserved,
               COALESCE(SUM(i.quantity_damaged),0)::bigint AS quantity_damaged,
               COALESCE(SUM(i.quantity_quarantined),0)::bigint AS quantity_quarantined
        FROM prism_data.products p LEFT JOIN prism_data.inventory i ON i.product_id = p.product_id
        GROUP BY p.product_id ORDER BY p.product_name
    """),
    "products": ("Product catalogue", "SELECT product_id, sku, product_name, category, subcategory, brand, model, unit, weight_kg, storage_requirement, fragile_flag, customer_id FROM prism_data.products ORDER BY product_name"),
    "customers": ("Customers and contracts", "SELECT customer_id, company_name, contact_person, contact_email, contact_phone, allocated_area_sqft, contract_start, contract_end, status FROM prism_data.customers ORDER BY company_name"),
    "orders": ("Customer orders", OPERATIONS_QUERIES["orders"][0]),
    "inbound": ("Inbound transactions", OPERATIONS_QUERIES["inbound"][0]),
    "outbound": ("Outbound transactions (source values)", OPERATIONS_QUERIES["outbound"][0]),
    "returns": ("Returns and damage", OPERATIONS_QUERIES["returns"][0]),
    "movements": ("Stock movements", OPERATIONS_QUERIES["movements"][0]),
    "workforce": ("Workforce roster", "SELECT worker_id, name, role, staff_or_trainee, skill, assigned_area_id, assigned_zone_id, shift, joining_date, status, attendance_status FROM prism_data.workers ORDER BY name"),
    "compliance": ("Certification register", "SELECT cert_id, owner_type, customer_id, product_id, certificate_type, certificate_no, issuing_authority, issue_date, expiry_date, verification_status FROM prism_data.certifications ORDER BY expiry_date"),
    "locations": ("Storage locations", "SELECT location_id, segment_id, rack_no, shelf_no, bin_no, location_type, capacity_units, occupied_units, status FROM prism_data.storage_locations ORDER BY location_id"),
}


@router.get("/reports")
def list_reports():
    return {"items": [{"key": key, "title": title, "format": "CSV", "download_endpoint": f"/api/reports/{key}/download", "preview_endpoint": f"/api/reports/{key}/preview"}
                     for key, (title, _) in REPORTS.items()],
            "note": "Reports are generated from current database records at download time. PDF generation is not configured."}


@router.get("/reports/{report_key}/preview")
def preview_report(report_key: str, limit: int = Query(default=25, ge=1, le=100), db: Session = Depends(get_db)):
    if report_key not in REPORTS:
        raise HTTPException(status_code=404, detail="Unknown report key.")
    title, sql = REPORTS[report_key]
    try:
        rows = _all(db, f"SELECT * FROM ({sql}) AS report_source LIMIT :limit", {"limit": limit})
        count_sql = f"SELECT COUNT(*) AS n FROM ({sql}) AS report_source"
        total = _int((_one(db, count_sql) or {}).get("n"))
    except SQLAlchemyError as exc:
        raise _missing_data_schema_error() from exc
    return {"key": report_key, "title": title, "columns": list(rows[0].keys()) if rows else [], "items": rows, "total": total}


@router.get("/reports/{report_key}/download")
def download_report(report_key: str, db: Session = Depends(get_db)):
    if report_key not in REPORTS:
        raise HTTPException(status_code=404, detail="Unknown report key.")
    title, sql = REPORTS[report_key]
    try:
        rows = _all(db, sql)
        output = io.StringIO()
        if rows:
            writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()), extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()})
        else:
            output.write("no_records\n")
        db.execute(text("""
            INSERT INTO prism_app.report_runs (report_key, report_title, row_count, generated_by)
            VALUES (:key, :title, :row_count, 'Warehouse Manager')
        """), {"key": report_key, "title": title, "row_count": len(rows)})
        db.execute(text("""
            INSERT INTO prism_app.audit_events (event_type, actor_label, entity_type, entity_id, details_json)
            VALUES ('REPORT_EXPORTED', 'Warehouse Manager', 'report', :key, CAST(:details AS jsonb))
        """), {"key": report_key, "details": json.dumps({"row_count": len(rows), "format": "CSV"})})
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise _app_schema_error() from exc
    safe_title = "_".join(title.lower().split())
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="prism_{safe_title}.csv"'})


@router.get("/audit/events")
def list_audit_events(limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)):
    try:
        items = _all(db, "SELECT audit_event_id, event_type, actor_label, entity_type, entity_id, details_json, event_at FROM prism_app.audit_events ORDER BY event_at DESC LIMIT :limit", {"limit": limit})
    except SQLAlchemyError as exc:
        raise _app_schema_error() from exc
    return {"items": items, "total_returned": len(items)}
