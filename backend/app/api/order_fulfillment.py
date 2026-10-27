"""Transactional PRISM order reservation, picking, packing and dispatch workflows."""
from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(prefix="/api/workflows", tags=["PRISM Order & Outbound Workflows"])


def one(db: Session, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    row = db.execute(text(sql), params or {}).mappings().first()
    return dict(row) if row else None


def many(db: Session, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return [dict(row) for row in db.execute(text(sql), params or {}).mappings().all()]


class ReserveRequest(BaseModel):
    request_key: str = Field(min_length=16, max_length=80)
    order_id: str = Field(min_length=1, max_length=100)
    worker_id: str = Field(min_length=1, max_length=100)
    destination: str = Field(min_length=2, max_length=200)


class ActionRequest(BaseModel):
    request_key: str = Field(min_length=16, max_length=80)


class DispatchRequest(ActionRequest):
    vehicle_no: str = Field(min_length=1, max_length=80)


def claim(db: Session, key: str, kind: str) -> dict[str, Any] | None:
    """Claim an idempotency key, or return the response saved for an earlier retry."""
    prior = one(
        db,
        """
        SELECT operation_type, response_json
        FROM prism_app.operation_requests
        WHERE request_key = :key
        """,
        {"key": key},
    )

    if prior:
        db.rollback()
        if prior["operation_type"] != kind:
            raise HTTPException(409, "This request key was used for another action. Refresh and retry.")
        response = prior.get("response_json") or {}
        if response:
            return {**response, "idempotent_replay": True}
        raise HTTPException(409, "This request is already being processed. Try again shortly.")

    inserted = one(
        db,
        """
        INSERT INTO prism_app.operation_requests
            (request_key, operation_type, response_json)
        VALUES (:key, :kind, '{}'::jsonb)
        ON CONFLICT (request_key) DO NOTHING
        RETURNING request_key
        """,
        {"key": key, "kind": kind},
    )

    if not inserted:
        db.rollback()
        raise HTTPException(409, "This request is already being processed. Refresh and retry.")

    return None


def finish(db: Session, key: str, response: dict[str, Any]) -> dict[str, Any]:
    db.execute(
        text("""
            UPDATE prism_app.operation_requests
            SET response_json = CAST(:body AS jsonb),
                completed_at = CURRENT_TIMESTAMP
            WHERE request_key = :key
        """),
        {"body": json.dumps(response), "key": key},
    )
    db.commit()
    return response


def activity(
    db: Session,
    worker_id: str,
    action: str,
    fulfillment_id: str,
    detail: str,
) -> None:
    db.execute(
        text("""
            INSERT INTO prism_data.activity_log
                (activity_id, worker_id, action_type, entity_type,
                 entity_id, timestamp, description)
            VALUES
                (:id, :worker, :action, 'outbound',
                 :entity, CURRENT_TIMESTAMP, :detail)
        """),
        {
            "id": "ACT-OP-" + uuid.uuid4().hex[:12].upper(),
            "worker": worker_id,
            "action": action,
            "entity": fulfillment_id,
            "detail": detail,
        },
    )


def audit(
    db: Session,
    event: str,
    actor: str,
    fulfillment_id: str,
    detail: dict[str, Any],
) -> None:
    db.execute(
        text("""
            INSERT INTO prism_app.audit_events
                (event_type, actor_label, entity_type, entity_id, details_json)
            VALUES
                (:event, :actor, 'outbound', :entity,
                 CAST(:detail AS jsonb))
        """),
        {
            "event": event,
            "actor": actor,
            "entity": fulfillment_id,
            "detail": json.dumps(detail),
        },
    )


@router.get("/outbound-options")
def outbound_options(db: Session = Depends(get_db)):
    """List open orders, eligible workers, and live fulfillment jobs."""
    try:
        orders = many(
            db,
            """
            WITH owner_stock AS (
                SELECT
                    i.product_id,
                    a.customer_id,
                    SUM(COALESCE(i.quantity_available, 0))::bigint AS available_units
                FROM prism_data.inventory i
                JOIN prism_data.storage_locations sl
                    ON sl.location_id = i.location_id
                JOIN prism_data.segments sg
                    ON sg.segment_id = sl.segment_id
                JOIN prism_data.zones z
                    ON z.zone_id = sg.zone_id
                JOIN prism_data.areas a
                    ON a.area_id = z.area_id
                GROUP BY i.product_id, a.customer_id
            )
            SELECT
                o.order_id,
                o.customer_id,
                c.company_name AS customer_name,
                o.product_id,
                p.product_name,
                p.sku,
                p.customer_id AS product_customer_id,
                o.quantity,
                o.priority,
                o.order_date,
                o.requested_dispatch_date,
                o.status,
                COALESCE(s.available_units, 0)::bigint AS available_units
            FROM prism_data.orders o
            JOIN prism_data.customers c
                ON c.customer_id = o.customer_id
            JOIN prism_data.products p
                ON p.product_id = o.product_id
            LEFT JOIN owner_stock s
                ON s.product_id = o.product_id
               AND s.customer_id = o.customer_id
            WHERE LOWER(o.status) IN ('pending', 'processing')
              AND NOT EXISTS (
                  SELECT 1
                  FROM prism_app.order_fulfillments f
                  WHERE f.order_id = o.order_id
                    AND f.status <> 'CANCELLED'
              )
            ORDER BY
                CASE
                    WHEN LOWER(o.priority) IN ('critical', 'urgent') THEN 0
                    WHEN LOWER(o.priority) = 'high' THEN 1
                    ELSE 2
                END,
                o.requested_dispatch_date,
                o.order_date,
                o.order_id
            """,
        )

        workers = many(
            db,
            """
            SELECT worker_id, name, role, skill, shift
            FROM prism_data.workers
            WHERE LOWER(status) = 'active'
              AND LOWER(attendance_status) = 'present'
            ORDER BY name
            """,
        )

        fulfillments = many(
            db,
            """
            SELECT
                f.fulfillment_id,
                f.order_id,
                f.customer_id,
                c.company_name AS customer_name,
                f.product_id,
                p.product_name,
                p.sku,
                f.requested_qty,
                f.status,
                f.assigned_worker_id,
                w.name AS worker_name,
                f.destination,
                f.vehicle_no,
                f.created_at,
                f.updated_at,
                f.dispatched_at,
                o.priority,
                ob.delivery_status
            FROM prism_app.order_fulfillments f
            JOIN prism_data.orders o ON o.order_id = f.order_id
            JOIN prism_data.customers c ON c.customer_id = f.customer_id
            JOIN prism_data.products p ON p.product_id = f.product_id
            JOIN prism_data.workers w ON w.worker_id = f.assigned_worker_id
            LEFT JOIN prism_data.outbound_transactions ob
                ON ob.outbound_id = f.fulfillment_id
            ORDER BY f.created_at DESC
            LIMIT 200
            """,
        )

    except SQLAlchemyError as exc:
        raise HTTPException(
            503,
            "Outbound workflow tables are unavailable. Run the order fulfillment SQL migration.",
        ) from exc

    for row in orders:
        available = int(row.get("available_units") or 0)
        qty = int(row.get("quantity") or 0)
        owner_ok = row["customer_id"] == row["product_customer_id"]

        row["can_reserve"] = owner_ok and qty > 0 and available >= qty

        if row["can_reserve"]:
            row["blocked_reason"] = None
        elif not owner_ok:
            row["blocked_reason"] = (
                "Order customer does not match the product owner; review required."
            )
        elif qty <= 0:
            row["blocked_reason"] = "Order quantity must be greater than zero."
        else:
            row["blocked_reason"] = (
                f"Insufficient stock: {available} available, {qty} requested."
            )

    return {
        "orders": orders,
        "workers": workers,
        "fulfillments": fulfillments,
    }


@router.post("/order-fulfillments/reserve")
def reserve_order(payload: ReserveRequest, db: Session = Depends(get_db)):
    replay = claim(db, payload.request_key, "OUTBOUND_RESERVE")
    if replay is not None:
        return replay

    try:
        order = one(
            db,
            """
            SELECT
                o.order_id,
                o.customer_id,
                o.product_id,
                o.quantity,
                o.status,
                c.company_name AS customer_name,
                p.product_name,
                p.sku,
                p.customer_id AS product_customer_id
            FROM prism_data.orders o
            JOIN prism_data.customers c ON c.customer_id = o.customer_id
            JOIN prism_data.products p ON p.product_id = o.product_id
            WHERE o.order_id = :order_id
            FOR UPDATE OF o
            """,
            {"order_id": payload.order_id},
        )

        if not order:
            raise HTTPException(404, "Choose an existing order.")

        if str(order["status"]).lower() not in {"pending", "processing"}:
            raise HTTPException(
                409,
                f"Order is not open for fulfillment (status: {order['status']}).",
            )

        if order["customer_id"] != order["product_customer_id"]:
            raise HTTPException(
                409,
                "Order customer does not match product owner; this record requires review.",
            )

        qty = int(order["quantity"] or 0)
        if qty <= 0:
            raise HTTPException(422, "Order quantity must be greater than zero.")

        existing = one(
            db,
            """
            SELECT fulfillment_id, status
            FROM prism_app.order_fulfillments
            WHERE order_id = :order_id
              AND status <> 'CANCELLED'
            FOR UPDATE
            """,
            {"order_id": payload.order_id},
        )

        if existing:
            raise HTTPException(
                409,
                f"Order already has active fulfillment {existing['fulfillment_id']} "
                f"({existing['status']}).",
            )

        worker = one(
            db,
            """
            SELECT worker_id, name
            FROM prism_data.workers
            WHERE worker_id = :worker
              AND LOWER(status) = 'active'
              AND LOWER(attendance_status) = 'present'
            """,
            {"worker": payload.worker_id},
        )

        if not worker:
            raise HTTPException(422, "Choose an active worker marked present.")

        stock = many(
            db,
            """
            SELECT i.inventory_id, i.location_id, i.quantity_available
            FROM prism_data.inventory i
            JOIN prism_data.storage_locations sl
                ON sl.location_id = i.location_id
            JOIN prism_data.segments sg ON sg.segment_id = sl.segment_id
            JOIN prism_data.zones z ON z.zone_id = sg.zone_id
            JOIN prism_data.areas a ON a.area_id = z.area_id
            WHERE i.product_id = :product
              AND a.customer_id = :customer
              AND COALESCE(i.quantity_available, 0) > 0
            ORDER BY sl.location_id, i.inventory_id
            FOR UPDATE OF i
            """,
            {
                "product": order["product_id"],
                "customer": order["customer_id"],
            },
        )

        available = sum(int(s["quantity_available"] or 0) for s in stock)
        if available < qty:
            raise HTTPException(
                409,
                f"Insufficient stock: {available} available; {qty} required.",
            )

        allocations = []
        remaining = qty

        for stock_row in stock:
            take = min(
                int(stock_row["quantity_available"] or 0),
                remaining,
            )

            if take > 0:
                allocations.append({
                    "inventory_id": stock_row["inventory_id"],
                    "location_id": stock_row["location_id"],
                    "quantity": take,
                })
                remaining -= take

            if remaining == 0:
                break

        if remaining:
            raise HTTPException(
                409,
                "Stock availability changed during reservation. Refresh and retry.",
            )

        fulfillment_id = "OUT-OP-" + uuid.uuid4().hex[:12].upper()
        destination = payload.destination.strip()

        if not destination:
            raise HTTPException(422, "Destination cannot be blank.")

        db.execute(
            text("""
                INSERT INTO prism_app.order_fulfillments (
                    fulfillment_id, order_id, customer_id, product_id,
                    requested_qty, status, assigned_worker_id, destination,
                    prior_order_status
                )
                VALUES (
                    :id, :order, :customer, :product,
                    :qty, 'RESERVED', :worker, :destination, :prior
                )
            """),
            {
                "id": fulfillment_id,
                "order": order["order_id"],
                "customer": order["customer_id"],
                "product": order["product_id"],
                "qty": qty,
                "worker": worker["worker_id"],
                "destination": destination,
                "prior": order["status"],
            },
        )

        for allocation in allocations:
            result = db.execute(
                text("""
                    UPDATE prism_data.inventory
                    SET quantity_available = quantity_available - :qty,
                        quantity_reserved = quantity_reserved + :qty,
                        last_updated = CURRENT_DATE
                    WHERE inventory_id = :id
                      AND quantity_available >= :qty
                """),
                {
                    "qty": allocation["quantity"],
                    "id": allocation["inventory_id"],
                },
            )

            if result.rowcount != 1:
                raise HTTPException(
                    409,
                    "Stock changed during reservation; refresh and retry.",
                )

            db.execute(
                text("""
                    INSERT INTO prism_app.order_fulfillment_allocations (
                        fulfillment_id, inventory_id, location_id, quantity
                    )
                    VALUES (:f, :i, :l, :q)
                """),
                {
                    "f": fulfillment_id,
                    "i": allocation["inventory_id"],
                    "l": allocation["location_id"],
                    "q": allocation["quantity"],
                },
            )

        db.execute(
            text("""
                INSERT INTO prism_data.outbound_transactions (
                    outbound_id, customer_id, order_id, product_id,
                    requested_qty, picked_qty, packed_qty, dispatch_datetime,
                    destination, vehicle_no, delivery_status
                )
                VALUES (
                    :id, :customer, :order, :product,
                    :qty, 0, 0, NULL, :destination, NULL, 'Reserved'
                )
            """),
            {
                "id": fulfillment_id,
                "customer": order["customer_id"],
                "order": order["order_id"],
                "product": order["product_id"],
                "qty": qty,
                "destination": destination,
            },
        )

        db.execute(
            text("""
                UPDATE prism_data.orders
                SET status = 'Processing'
                WHERE order_id = :order
            """),
            {"order": order["order_id"]},
        )

        activity(
            db,
            worker["worker_id"],
            "ORDER_RESERVED",
            fulfillment_id,
            f"Reserved {qty} units for order {order['order_id']}.",
        )

        audit(
            db,
            "OUTBOUND_RESERVED",
            worker["name"],
            fulfillment_id,
            {
                "order_id": order["order_id"],
                "product_id": order["product_id"],
                "quantity": qty,
                "allocations": allocations,
                "destination": destination,
            },
        )

        return finish(
            db,
            payload.request_key,
            {
                "message": "Stock reserved and fulfillment started.",
                "fulfillment_id": fulfillment_id,
                "order_id": order["order_id"],
                "product_id": order["product_id"],
                "product_name": order["product_name"],
                "requested_qty": qty,
                "status": "RESERVED",
                "allocations": allocations,
                "available_units_before": available,
                "available_units_after": available - qty,
                "worker_name": worker["name"],
                "idempotent_replay": False,
            },
        )

    except HTTPException:
        db.rollback()
        raise

    except SQLAlchemyError as exc:
        db.rollback()
        if "prism_app" in str(exc).lower() or "order_fulfillment" in str(exc).lower():
            raise HTTPException(
                503,
                "Order fulfillment tables are unavailable. Run the order fulfillment SQL migration.",
            ) from exc
        raise HTTPException(
            500,
            "Reservation failed; the database transaction was rolled back.",
        ) from exc


def advance(
    fulfillment_id: str,
    payload: ActionRequest,
    expected: str,
    target: str,
    operation: str,
    event: str,
    delivery: str,
    picked: bool,
    packed: bool,
    db: Session,
) -> dict[str, Any]:
    replay = claim(db, payload.request_key, operation)
    if replay is not None:
        return replay

    try:
        fulfillment = one(
            db,
            """
            SELECT f.*, w.name AS worker_name
            FROM prism_app.order_fulfillments f
            JOIN prism_data.workers w
                ON w.worker_id = f.assigned_worker_id
            WHERE f.fulfillment_id = :id
            FOR UPDATE OF f
            """,
            {"id": fulfillment_id},
        )

        if not fulfillment:
            raise HTTPException(404, "Live fulfillment not found.")

        if fulfillment["status"] != expected:
            raise HTTPException(
                409,
                f"Invalid transition: current status is {fulfillment['status']}; "
                f"expected {expected}.",
            )

        db.execute(
            text("""
                UPDATE prism_app.order_fulfillments
                SET status = :status, updated_at = CURRENT_TIMESTAMP
                WHERE fulfillment_id = :id
            """),
            {"status": target, "id": fulfillment_id},
        )

        db.execute(
            text("""
                UPDATE prism_data.outbound_transactions
                SET picked_qty = CASE WHEN :picked THEN requested_qty ELSE picked_qty END,
                    packed_qty = CASE WHEN :packed THEN requested_qty ELSE packed_qty END,
                    delivery_status = :delivery
                WHERE outbound_id = :id
            """),
            {
                "picked": picked,
                "packed": packed,
                "delivery": delivery,
                "id": fulfillment_id,
            },
        )

        activity(
            db,
            fulfillment["assigned_worker_id"],
            event,
            fulfillment_id,
            f"Order {fulfillment['order_id']} transitioned to {target}.",
        )

        audit(
            db,
            event,
            fulfillment["worker_name"],
            fulfillment_id,
            {
                "order_id": fulfillment["order_id"],
                "previous_status": expected,
                "status": target,
                "quantity": fulfillment["requested_qty"],
            },
        )

        return finish(
            db,
            payload.request_key,
            {
                "message": f"Fulfillment moved to {target.lower()}.",
                "fulfillment_id": fulfillment_id,
                "order_id": fulfillment["order_id"],
                "status": target,
                "idempotent_replay": False,
            },
        )

    except HTTPException:
        db.rollback()
        raise

    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            500,
            "Workflow transition failed; no partial changes were committed.",
        ) from exc


@router.post("/order-fulfillments/{fulfillment_id}/pick")
def pick_order(
    fulfillment_id: str,
    payload: ActionRequest,
    db: Session = Depends(get_db),
):
    return advance(
        fulfillment_id, payload,
        "RESERVED", "PICKED",
        "OUTBOUND_PICK", "ORDER_PICKED", "Picked",
        True, False, db,
    )


@router.post("/order-fulfillments/{fulfillment_id}/pack")
def pack_order(
    fulfillment_id: str,
    payload: ActionRequest,
    db: Session = Depends(get_db),
):
    return advance(
        fulfillment_id, payload,
        "PICKED", "PACKED",
        "OUTBOUND_PACK", "ORDER_PACKED", "Packed",
        True, True, db,
    )


@router.post("/order-fulfillments/{fulfillment_id}/dispatch")
def dispatch_order(
    fulfillment_id: str,
    payload: DispatchRequest,
    db: Session = Depends(get_db),
):
    replay = claim(db, payload.request_key, "OUTBOUND_DISPATCH")
    if replay is not None:
        return replay

    vehicle = payload.vehicle_no.strip()
    if not vehicle:
        db.rollback()
        raise HTTPException(422, "Vehicle number cannot be blank.")

    try:
        fulfillment = one(
            db,
            """
            SELECT f.*, w.name AS worker_name
            FROM prism_app.order_fulfillments f
            JOIN prism_data.workers w
                ON w.worker_id = f.assigned_worker_id
            WHERE f.fulfillment_id = :id
            FOR UPDATE OF f
            """,
            {"id": fulfillment_id},
        )

        if not fulfillment:
            raise HTTPException(404, "Live fulfillment not found.")

        if fulfillment["status"] != "PACKED":
            raise HTTPException(
                409,
                f"Dispatch requires PACKED status; current status is {fulfillment['status']}.",
            )

        allocations = many(
            db,
            """
            SELECT a.inventory_id, a.location_id, a.quantity, i.quantity_reserved
            FROM prism_app.order_fulfillment_allocations a
            JOIN prism_data.inventory i ON i.inventory_id = a.inventory_id
            WHERE a.fulfillment_id = :id
            ORDER BY a.location_id, a.inventory_id
            FOR UPDATE OF i
            """,
            {"id": fulfillment_id},
        )

        if (
            not allocations
            or sum(int(a["quantity"]) for a in allocations)
            != int(fulfillment["requested_qty"])
        ):
            raise HTTPException(
                409,
                "Allocation ledger is incomplete; dispatch is blocked to protect stock balances.",
            )

        qty_by_location: dict[str, int] = {}

        for allocation in allocations:
            if int(allocation["quantity_reserved"] or 0) < int(allocation["quantity"]):
                raise HTTPException(
                    409,
                    f"Reserved stock changed for {allocation['inventory_id']}; "
                    "dispatch is blocked for reconciliation.",
                )
            loc = allocation["location_id"]
            qty_by_location[loc] = qty_by_location.get(loc, 0) + int(allocation["quantity"])

        # Lock the affected locations and their parent hierarchy. Historical
        # occupancy counters may be stale, so do not reject dispatch merely
        # because an old occupied_units value is lower than this allocation.
        hierarchy: dict[str, dict[str, Any]] = {}

        for loc in sorted(qty_by_location):
            row = one(
                db,
                """
                SELECT
                    sl.location_id,
                    sl.capacity_units AS loc_capacity,
                    sl.segment_id,
                    sg.zone_id,
                    z.area_id
                FROM prism_data.storage_locations sl
                JOIN prism_data.segments sg ON sg.segment_id = sl.segment_id
                JOIN prism_data.zones z ON z.zone_id = sg.zone_id
                JOIN prism_data.areas a ON a.area_id = z.area_id
                WHERE sl.location_id = :loc
                FOR UPDATE OF sl, sg, z, a
                """,
                {"loc": loc},
            )

            if not row:
                raise HTTPException(
                    409,
                    f"Storage location {loc} is missing from the capacity hierarchy.",
                )
            hierarchy[loc] = row

        # Dispatch consumes the reservation. Available stock was already
        # reduced when the order was reserved; do not deduct it a second time.
        for allocation in allocations:
            result = db.execute(
                text("""
                    UPDATE prism_data.inventory
                    SET quantity_reserved = quantity_reserved - :qty,
                        last_updated = CURRENT_DATE
                    WHERE inventory_id = :id
                      AND quantity_reserved >= :qty
                """),
                {
                    "qty": allocation["quantity"],
                    "id": allocation["inventory_id"],
                },
            )

            if result.rowcount != 1:
                raise HTTPException(
                    409,
                    "Reserved stock changed; dispatch was cancelled safely.",
                )

        touched_segments: set[str] = set()
        touched_zones: set[str] = set()
        touched_areas: set[str] = set()

        # Recalculate affected location occupancy using all stock states that
        # physically occupy space. This repairs stale imported counters for
        # affected locations without modifying unrelated locations.
        for loc, row in hierarchy.items():
            stock = one(
                db,
                """
                SELECT COALESCE(
                    SUM(
                        COALESCE(quantity_available, 0)
                        + COALESCE(quantity_reserved, 0)
                        + COALESCE(quantity_damaged, 0)
                        + COALESCE(quantity_quarantined, 0)
                    ),
                    0
                )::bigint AS occupied
                FROM prism_data.inventory
                WHERE location_id = :loc
                """,
                {"loc": loc},
            )

            occupied = int((stock or {}).get("occupied") or 0)
            capacity = int(row["loc_capacity"] or 0)

            if capacity > 0 and occupied > capacity:
                raise HTTPException(
                    409,
                    f"Inventory at {loc} exceeds its recorded capacity after reconciliation; "
                    "dispatch was rolled back for review.",
                )

            location_status = (
                "Available" if occupied == 0
                else "Full" if capacity > 0 and occupied >= capacity
                else "Occupied"
            )

            db.execute(
                text("""
                    UPDATE prism_data.storage_locations
                    SET occupied_units = :occupied, status = :status
                    WHERE location_id = :loc
                """),
                {"occupied": occupied, "status": location_status, "loc": loc},
            )

            touched_segments.add(row["segment_id"])
            touched_zones.add(row["zone_id"])
            touched_areas.add(row["area_id"])

        # Recalculate parent occupancy from the storage-location counters
        # rather than decrementing parent values that may also be stale.
        for segment_id in touched_segments:
            db.execute(
                text("""
                    UPDATE prism_data.segments
                    SET occupied_units = (
                        SELECT COALESCE(SUM(sl.occupied_units), 0)
                        FROM prism_data.storage_locations sl
                        WHERE sl.segment_id = :id
                    )
                    WHERE segment_id = :id
                """),
                {"id": segment_id},
            )

        for zone_id in touched_zones:
            db.execute(
                text("""
                    UPDATE prism_data.zones
                    SET occupied_units = (
                        SELECT COALESCE(SUM(sl.occupied_units), 0)
                        FROM prism_data.storage_locations sl
                        JOIN prism_data.segments sg
                            ON sg.segment_id = sl.segment_id
                        WHERE sg.zone_id = :id
                    )
                    WHERE zone_id = :id
                """),
                {"id": zone_id},
            )

        for area_id in touched_areas:
            area = one(
                db,
                "SELECT capacity_units FROM prism_data.areas WHERE area_id = :id",
                {"id": area_id},
            )
            occupied = one(
                db,
                """
                SELECT COALESCE(SUM(sl.occupied_units), 0)::bigint AS occupied
                FROM prism_data.storage_locations sl
                JOIN prism_data.segments sg ON sg.segment_id = sl.segment_id
                JOIN prism_data.zones z ON z.zone_id = sg.zone_id
                WHERE z.area_id = :id
                """,
                {"id": area_id},
            )

            capacity = int((area or {}).get("capacity_units") or 0)
            total_occupied = int((occupied or {}).get("occupied") or 0)
            if capacity > 0:
                db.execute(
                    text("""
                        UPDATE prism_data.areas
                        SET utilization_pct = :pct
                        WHERE area_id = :id
                    """),
                    {
                        "pct": round(total_occupied * 100.0 / capacity, 2),
                        "id": area_id,
                    },
                )

        db.execute(
            text("""
                UPDATE prism_data.outbound_transactions
                SET dispatch_datetime = CURRENT_TIMESTAMP,
                    vehicle_no = :vehicle,
                    delivery_status = 'Dispatched'
                WHERE outbound_id = :id
            """),
            {"vehicle": vehicle, "id": fulfillment_id},
        )

        db.execute(
            text("""
                UPDATE prism_data.orders
                SET status = 'Completed'
                WHERE order_id = :id
            """),
            {"id": fulfillment["order_id"]},
        )

        db.execute(
            text("""
                UPDATE prism_app.order_fulfillments
                SET status = 'DISPATCHED',
                    vehicle_no = :vehicle,
                    dispatched_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE fulfillment_id = :id
            """),
            {"vehicle": vehicle, "id": fulfillment_id},
        )

        activity(
            db,
            fulfillment["assigned_worker_id"],
            "ORDER_DISPATCHED",
            fulfillment_id,
            f"Dispatched order {fulfillment['order_id']} in vehicle {vehicle}.",
        )

        audit(
            db,
            "OUTBOUND_DISPATCHED",
            fulfillment["worker_name"],
            fulfillment_id,
            {
                "order_id": fulfillment["order_id"],
                "quantity": fulfillment["requested_qty"],
                "vehicle_no": vehicle,
                "allocations": allocations,
            },
        )

        return finish(
            db,
            payload.request_key,
            {
                "message": "Order dispatched successfully.",
                "fulfillment_id": fulfillment_id,
                "order_id": fulfillment["order_id"],
                "status": "DISPATCHED",
                "vehicle_no": vehicle,
                "idempotent_replay": False,
            },
        )

    except HTTPException:
        db.rollback()
        raise

    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            500,
            "Dispatch failed; the database transaction was rolled back.",
        ) from exc