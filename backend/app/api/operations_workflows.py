"""Transactional non-agent warehouse workflows for PRISM.

This router is additive. Historical source rows are preserved; newly entered receipts are
written as new operational records and applied to stock in the same PostgreSQL transaction.
Agent implementations are deliberately not imported here.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Literal, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(prefix="/api/workflows", tags=["PRISM Operational Workflows"])


def _one(db: Session, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    row = db.execute(text(sql), params or {}).mappings().first()
    return dict(row) if row is not None else None


def _all(db: Session, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return [dict(row) for row in db.execute(text(sql), params or {}).mappings().all()]


def _data_error() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail="PRISM operational tables are unavailable. Confirm the prism_data dataset import completed successfully.",
    )


def _app_error() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail="PRISM workflow idempotency storage is unavailable. Run sql/002_prism_operation_requests.sql in prism_db.",
    )


def _storage_compatible(requirement: str | None, location_type: str | None) -> bool:
    req = (requirement or "").strip().upper()
    loc = (location_type or "").strip().upper()
    if req == "SECURE_RACK":
        return loc == "SECURE_RACK"
    if req == "INDOOR_RACK":
        return loc in {"RACK", "SECURE_RACK"}
    # The current dataset has no FLOOR location type. Unknown requirements require an explicit override.
    return False


class InboundReceiptRequest(BaseModel):
    request_key: str = Field(min_length=16, max_length=80)
    product_id: str = Field(min_length=1, max_length=100)
    supplier: str = Field(min_length=1, max_length=200)
    expected_qty: int = Field(ge=1, le=1_000_000)
    received_qty: int = Field(ge=1, le=1_000_000)
    damaged_qty: int = Field(ge=0, le=1_000_000)
    location_id: str = Field(min_length=1, max_length=100)
    batch_no: str = Field(min_length=1, max_length=100)
    serial_tracking_type: Literal["Batch", "Serial"] = "Batch"
    worker_id: str = Field(min_length=1, max_length=100)
    inspection_status: Literal["Passed", "Pending", "Failed"] = "Pending"
    certification_status: Literal["Verified", "Pending"] = "Pending"
    arrival_datetime: datetime | None = None
    storage_override: bool = False
    override_reason: str | None = Field(default=None, max_length=1000)


@router.get("/inbound-options")
def inbound_options(db: Session = Depends(get_db)):
    """Lookup data for the receipt form; no rows are changed."""
    try:
        products = _all(db, """
            SELECT p.product_id, p.sku, p.product_name, p.customer_id,
                   c.company_name AS customer_name, p.storage_requirement, p.unit
            FROM prism_data.products p
            JOIN prism_data.customers c ON c.customer_id = p.customer_id
            ORDER BY p.product_name
        """)
        locations = _all(db, """
            SELECT sl.location_id, sl.location_type, sl.capacity_units, sl.occupied_units,
                   GREATEST(sl.capacity_units - sl.occupied_units, 0)::bigint AS remaining_capacity_units,
                   sl.status, a.customer_id AS area_customer_id, sg.segment_name, z.zone_name, a.area_name
            FROM prism_data.storage_locations sl
            JOIN prism_data.segments sg ON sg.segment_id = sl.segment_id
            JOIN prism_data.zones z ON z.zone_id = sg.zone_id
            JOIN prism_data.areas a ON a.area_id = z.area_id
            ORDER BY a.area_name, z.zone_name, sl.location_id
        """)
        workers = _all(db, """
            SELECT worker_id, name, role, skill, shift
            FROM prism_data.workers
            WHERE LOWER(status) = 'active' AND LOWER(attendance_status) = 'present'
            ORDER BY name
        """)
    except SQLAlchemyError as exc:
        raise _data_error() from exc
    return {"products": products, "locations": locations, "workers": workers}


@router.post("/inbound-receipts")
def record_inbound_receipt(payload: InboundReceiptRequest, db: Session = Depends(get_db)):
    """Record a new receipt exactly once and apply stock/capacity changes atomically.

    Historical inbound rows are never replayed or imported again. `request_key` makes retrying
    this same UI submission idempotent so network retries cannot double-count stock.
    """
    if not payload.supplier.strip():
        raise HTTPException(status_code=422, detail="Supplier name cannot be blank.")
    if not payload.batch_no.strip():
        raise HTTPException(status_code=422, detail="Batch/lot number cannot be blank.")
    if payload.received_qty > payload.expected_qty:
        raise HTTPException(status_code=422, detail="Received quantity cannot exceed expected quantity for this receipt. Record an explicit over-receipt workflow separately if needed.")
    if payload.damaged_qty > payload.received_qty:
        raise HTTPException(status_code=422, detail="Damaged quantity cannot exceed received quantity.")
    if payload.storage_override and not (payload.override_reason or "").strip():
        raise HTTPException(status_code=422, detail="Provide a reason when overriding a product storage requirement.")
    if payload.arrival_datetime and payload.arrival_datetime.tzinfo is not None:
        raise HTTPException(status_code=422, detail="Arrival time must be a local date/time without a timezone offset.")

    try:
        prior = _one(db, """
            SELECT operation_type, response_json
            FROM prism_app.operation_requests
            WHERE request_key = :request_key
        """, {"request_key": payload.request_key})
    except SQLAlchemyError as exc:
        raise _app_error() from exc

    if prior:
        if prior["operation_type"] != "INBOUND_RECEIPT":
            raise HTTPException(status_code=409, detail="This request key was already used for a different operation. Refresh the form and retry.")
        response = prior.get("response_json") or {}
        if response:
            return {**response, "idempotent_replay": True}
        raise HTTPException(status_code=409, detail="This request is already being processed. Retry in a moment.")

    try:
        claimed = _one(db, """
            INSERT INTO prism_app.operation_requests (request_key, operation_type, response_json)
            VALUES (:request_key, 'INBOUND_RECEIPT', CAST('{}' AS jsonb))
            ON CONFLICT (request_key) DO NOTHING
            RETURNING request_key
        """, {"request_key": payload.request_key})
        if not claimed:
            # A concurrent request may have committed while this transaction waited on the unique key.
            prior = _one(db, """
                SELECT operation_type, response_json FROM prism_app.operation_requests
                WHERE request_key = :request_key
            """, {"request_key": payload.request_key})
            if prior and prior["operation_type"] == "INBOUND_RECEIPT" and prior.get("response_json"):
                db.rollback()
                return {**prior["response_json"], "idempotent_replay": True}
            db.rollback()
            raise HTTPException(status_code=409, detail="This request is already being processed. Retry in a moment.")

        product = _one(db, """
            SELECT p.product_id, p.customer_id, p.product_name, p.storage_requirement,
                   p.sku, c.company_name AS customer_name
            FROM prism_data.products p
            JOIN prism_data.customers c ON c.customer_id = p.customer_id
            WHERE p.product_id = :product_id
        """, {"product_id": payload.product_id})
        if not product:
            raise HTTPException(status_code=404, detail="Choose an existing PRISM product.")

        worker = _one(db, """
            SELECT worker_id, name FROM prism_data.workers
            WHERE worker_id = :worker_id AND LOWER(status) = 'active' AND LOWER(attendance_status) = 'present'
        """, {"worker_id": payload.worker_id})
        if not worker:
            raise HTTPException(status_code=422, detail="Choose a worker who is active and marked present.")

        # Lock the selected location and its capacity hierarchy so parallel receipts cannot overfill it.
        location = _one(db, """
            SELECT sl.location_id, sl.location_type, sl.capacity_units AS location_capacity,
                   sl.occupied_units AS location_occupied, sl.segment_id,
                   sg.capacity_units AS segment_capacity, sg.occupied_units AS segment_occupied,
                   sg.zone_id, z.capacity_units AS zone_capacity, z.occupied_units AS zone_occupied,
                   z.area_id, a.customer_id AS area_customer_id, a.capacity_units AS area_capacity
            FROM prism_data.storage_locations sl
            JOIN prism_data.segments sg ON sg.segment_id = sl.segment_id
            JOIN prism_data.zones z ON z.zone_id = sg.zone_id
            JOIN prism_data.areas a ON a.area_id = z.area_id
            WHERE sl.location_id = :location_id
            FOR UPDATE OF sl, sg, z, a
        """, {"location_id": payload.location_id})
        if not location:
            raise HTTPException(status_code=404, detail="Choose an existing storage location.")
        if location.get("area_customer_id") != product.get("customer_id"):
            raise HTTPException(status_code=409, detail="This storage location belongs to a different customer area. Choose a location allocated to the product owner.")

        compatible = _storage_compatible(product.get("storage_requirement"), location.get("location_type"))
        if not compatible and not payload.storage_override:
            raise HTTPException(
                status_code=409,
                detail=(f"Product storage requirement '{product.get('storage_requirement')}' is not confirmed compatible with "
                        f"location type '{location.get('location_type')}'. Choose another location or explicitly record a storage override reason."),
            )

        for label, capacity_key, occupied_key in (
            ("storage location", "location_capacity", "location_occupied"),
            ("segment", "segment_capacity", "segment_occupied"),
            ("zone", "zone_capacity", "zone_occupied"),
        ):
            capacity = int(location.get(capacity_key) or 0)
            occupied = int(location.get(occupied_key) or 0)
            if capacity <= 0 or occupied + payload.received_qty > capacity:
                raise HTTPException(
                    status_code=409,
                    detail=f"Receipt cannot fit: {label} has {max(capacity - occupied, 0)} capacity units remaining, but {payload.received_qty} were received.",
                )

        area_capacity = int(location.get("area_capacity") or 0)
        if area_capacity <= 0:
            raise HTTPException(status_code=409, detail="The selected customer area has no valid capacity configured. Ask a manager to correct the warehouse configuration first.")
        area_occupied = _one(db, """
            SELECT COALESCE(SUM(sl.occupied_units), 0)::bigint AS occupied
            FROM prism_data.storage_locations sl
            JOIN prism_data.segments sg ON sg.segment_id = sl.segment_id
            JOIN prism_data.zones z ON z.zone_id = sg.zone_id
            WHERE z.area_id = :area_id
        """, {"area_id": location["area_id"]})
        area_used = int((area_occupied or {}).get("occupied") or 0)
        if area_used + payload.received_qty > area_capacity:
            raise HTTPException(status_code=409, detail=f"Receipt would exceed customer-area capacity. Available by current location occupancy: {max(area_capacity - area_used, 0)} units.")

        now = payload.arrival_datetime or datetime.now().replace(microsecond=0)
        good_qty = payload.received_qty - payload.damaged_qty
        quality_released = payload.inspection_status == "Passed" and payload.certification_status == "Verified"
        available_add = good_qty if quality_released else 0
        quarantine_add = good_qty - available_add
        inbound_id = "INB-OP-" + uuid.uuid4().hex[:12].upper()

        # Upsert stock to the exact product/location/batch line; the location row is already locked.
        stock_line = _one(db, """
            SELECT inventory_id FROM prism_data.inventory
            WHERE product_id = :product_id AND location_id = :location_id AND batch_no = :batch_no
            ORDER BY inventory_id LIMIT 1 FOR UPDATE
        """, {"product_id": payload.product_id, "location_id": payload.location_id, "batch_no": payload.batch_no})
        if stock_line:
            db.execute(text("""
                UPDATE prism_data.inventory
                SET quantity_available = COALESCE(quantity_available, 0) + :available_add,
                    quantity_damaged = COALESCE(quantity_damaged, 0) + :damaged_add,
                    quantity_quarantined = COALESCE(quantity_quarantined, 0) + :quarantine_add,
                    last_updated = CURRENT_DATE
                WHERE inventory_id = :inventory_id
            """), {
                "available_add": available_add,
                "damaged_add": payload.damaged_qty,
                "quarantine_add": quarantine_add,
                "inventory_id": stock_line["inventory_id"],
            })
            inventory_id = stock_line["inventory_id"]
        else:
            inventory_id = "INV-OP-" + uuid.uuid4().hex[:12].upper()
            db.execute(text("""
                INSERT INTO prism_data.inventory (
                    inventory_id, product_id, location_id, batch_no, serial_tracking_type,
                    quantity_available, quantity_reserved, quantity_damaged, quantity_quarantined, last_updated
                ) VALUES (
                    :inventory_id, :product_id, :location_id, :batch_no, :serial_tracking_type,
                    :available_add, 0, :damaged_add, :quarantine_add, CURRENT_DATE
                )
            """), {
                "inventory_id": inventory_id,
                "product_id": payload.product_id,
                "location_id": payload.location_id,
                "batch_no": payload.batch_no,
                "serial_tracking_type": payload.serial_tracking_type,
                "available_add": available_add,
                "damaged_add": payload.damaged_qty,
                "quarantine_add": quarantine_add,
            })

        # Update the capacity hierarchy in the same transaction.
        new_location_occupied = int(location["location_occupied"]) + payload.received_qty
        new_segment_occupied = int(location["segment_occupied"]) + payload.received_qty
        new_zone_occupied = int(location["zone_occupied"]) + payload.received_qty
        new_location_status = "Full" if new_location_occupied >= int(location["location_capacity"]) else "Occupied"
        db.execute(text("UPDATE prism_data.storage_locations SET occupied_units = :occupied, status = :status WHERE location_id = :location_id"), {
            "occupied": new_location_occupied, "status": new_location_status, "location_id": payload.location_id,
        })
        db.execute(text("UPDATE prism_data.segments SET occupied_units = :occupied WHERE segment_id = :segment_id"), {
            "occupied": new_segment_occupied, "segment_id": location["segment_id"],
        })
        db.execute(text("UPDATE prism_data.zones SET occupied_units = :occupied WHERE zone_id = :zone_id"), {
            "occupied": new_zone_occupied, "zone_id": location["zone_id"],
        })
        if area_capacity > 0:
            new_area_utilization = round(((area_used + payload.received_qty) / area_capacity) * 100, 2)
            db.execute(text("UPDATE prism_data.areas SET utilization_pct = :utilization WHERE area_id = :area_id"), {
                "utilization": new_area_utilization, "area_id": location["area_id"],
            })

        db.execute(text("""
            INSERT INTO prism_data.inbound_transactions (
                inbound_id, customer_id, supplier, product_id, expected_qty, received_qty, damaged_qty,
                arrival_datetime, inspection_status, certification_status, assigned_location_id
            ) VALUES (
                :inbound_id, :customer_id, :supplier, :product_id, :expected_qty, :received_qty, :damaged_qty,
                :arrival_datetime, :inspection_status, :certification_status, :location_id
            )
        """), {
            "inbound_id": inbound_id,
            "customer_id": product["customer_id"],
            "supplier": payload.supplier.strip(),
            "product_id": payload.product_id,
            "expected_qty": payload.expected_qty,
            "received_qty": payload.received_qty,
            "damaged_qty": payload.damaged_qty,
            "arrival_datetime": now,
            "inspection_status": payload.inspection_status,
            "certification_status": payload.certification_status,
            "location_id": payload.location_id,
        })

        db.execute(text("""
            INSERT INTO prism_data.activity_log (
                activity_id, worker_id, action_type, entity_type, entity_id, timestamp, description
            ) VALUES (
                :activity_id, :worker_id, 'INBOUND_RECEIPT_RECORDED', 'inbound', :entity_id, :event_time, :description
            )
        """), {
            "activity_id": "ACT-OP-" + uuid.uuid4().hex[:12].upper(),
            "worker_id": payload.worker_id,
            "entity_id": inbound_id,
            "event_time": now,
            "description": (
                f"Received {payload.received_qty} units of {product['sku']} at {payload.location_id}; "
                f"available +{available_add}, quarantined +{quarantine_add}, damaged +{payload.damaged_qty}."
            ),
        })

        db.execute(text("""
            INSERT INTO prism_app.audit_events (event_type, actor_label, entity_type, entity_id, details_json)
            VALUES ('INBOUND_RECEIPT_RECORDED', :actor_label, 'inbound', :entity_id, CAST(:details AS jsonb))
        """), {
            "actor_label": worker["name"],
            "entity_id": inbound_id,
            "details": json.dumps({
                "product_id": payload.product_id,
                "inventory_id": inventory_id,
                "location_id": payload.location_id,
                "received_qty": payload.received_qty,
                "available_added": available_add,
                "quarantined_added": quarantine_add,
                "damaged_added": payload.damaged_qty,
                "storage_requirement_override": (not compatible),
                "override_reason": payload.override_reason.strip() if payload.override_reason else None,
            }),
        })

        response = {
            "message": "Inbound receipt recorded successfully.",
            "inbound_id": inbound_id,
            "inventory_id": inventory_id,
            "product_id": payload.product_id,
            "product_name": product["product_name"],
            "location_id": payload.location_id,
            "received_qty": payload.received_qty,
            "available_added": available_add,
            "quarantined_added": quarantine_add,
            "damaged_added": payload.damaged_qty,
            "inspection_status": payload.inspection_status,
            "certification_status": payload.certification_status,
            "new_location_occupied_units": new_location_occupied,
            "location_capacity_units": int(location["location_capacity"]),
            "idempotent_replay": False,
        }
        db.execute(text("""
            UPDATE prism_app.operation_requests
            SET response_json = CAST(:response_json AS jsonb), completed_at = CURRENT_TIMESTAMP
            WHERE request_key = :request_key
        """), {"response_json": json.dumps(response), "request_key": payload.request_key})
        db.commit()
        return response
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Receipt could not be committed because a database operation failed. No partial stock or capacity update was committed.",
        ) from exc
