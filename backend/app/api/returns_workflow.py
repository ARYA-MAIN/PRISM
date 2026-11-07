"""Transactional Returns & Damage workflow for PRISM."""

from __future__ import annotations

import json
import uuid
from typing import Any, Literal
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(
    prefix="/api/workflows",
    tags=["PRISM Returns & Damage"],
)


def _one(
    db: Session,
    sql: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    row = db.execute(text(sql), params or {}).mappings().first()
    return dict(row) if row else None


def _all(
    db: Session,
    sql: str,
    params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rows = db.execute(text(sql), params or {}).mappings().all()
    return [dict(row) for row in rows]


def _storage_compatible(
    requirement: str | None,
    location_type: str | None,
) -> bool:
    requirement = (requirement or "").strip().upper()
    location_type = (location_type or "").strip().upper()

    if requirement == "SECURE_RACK":
        return location_type == "SECURE_RACK"

    if requirement == "INDOOR_RACK":
        return location_type in {"RACK", "SECURE_RACK"}

    # Unknown requirements, including FLOOR, require a future
    # explicit override workflow instead of silent acceptance.
    return False


class ReturnRequest(BaseModel):
    request_key: str = Field(min_length=16, max_length=80)
    customer_id: str = Field(min_length=1, max_length=100)
    product_id: str = Field(min_length=1, max_length=100)
    quantity: int = Field(ge=1, le=1_000_000)
    reason: str = Field(min_length=1, max_length=1000)

    damage_type: str = Field(default="None", max_length=100)
    inspection_result: Literal["Passed", "Pending", "Failed"]
    disposition: Literal["Restock", "Quarantine", "Damaged", "Dispose"]

    location_id: str | None = None
    worker_id: str = Field(min_length=1, max_length=100)


def _record_activity(
    db: Session,
    *,
    worker_id: str,
    return_id: str,
    product_id: str,
    quantity: int,
    disposition: str,
) -> None:
    """Write an activity entry when the existing activity-log schema supports it.

    Uses column metadata so this workflow can work with the activity-log
    naming already present in the project.
    """
    columns = _all(
        db,
        """
        SELECT column_name, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'prism_data'
          AND table_name = 'activity_log'
        ORDER BY ordinal_position
        """,
    )

    if not columns:
        return

    now_values: dict[str, Any] = {
        "worker_id": worker_id,
        "activity_type": "RETURN_PROCESSED",
        "activity": "RETURN_PROCESSED",
        "action_type": "RETURN_PROCESSED",
        "description": (
            f"Return {return_id}: {quantity} unit(s), "
            f"disposition {disposition}"
        ),
        "activity_description": (
            f"Return {return_id}: {quantity} unit(s), "
            f"disposition {disposition}"
        ),
        "details": json.dumps(
            {
                "return_id": return_id,
                "product_id": product_id,
                "quantity": quantity,
                "disposition": disposition,
            }
        ),
        "entity_type": "return",
        "entity_id": return_id,
        "timestamp": datetime.now(),
        "activity_date": datetime.now(),
        "created_at": datetime.now(),
    }

    insert_columns: list[str] = []
    insert_params: dict[str, Any] = {}

    for column in columns:
        name = column["column_name"]

        if name in now_values and now_values[name] is not None:
            insert_columns.append(name)
            insert_params[name] = now_values[name]

        elif name in {"timestamp", "activity_date", "created_at"}:
            insert_columns.append(name)
            insert_params[name] = None

    if not insert_columns:
        return

    quoted_columns = ", ".join(f'"{name}"' for name in insert_columns)
    placeholders = ", ".join(f":{name}" for name in insert_columns)

    # Activity logging is isolated so an optional legacy activity-log
    # column mismatch cannot leave stock partially updated.
    db.execute(text("SAVEPOINT return_activity_log"))

    try:
        db.execute(
            text(
                f"""
                INSERT INTO prism_data.activity_log ({quoted_columns})
                VALUES ({placeholders})
                """
            ),
            insert_params,
        )
        db.execute(text("RELEASE SAVEPOINT return_activity_log"))
    except SQLAlchemyError:
        db.execute(text("ROLLBACK TO SAVEPOINT return_activity_log"))
        db.execute(text("RELEASE SAVEPOINT return_activity_log"))


@router.get("/return-options")
def return_options(db: Session = Depends(get_db)):
    """Lookup data used by the Returns & Damage form."""
    try:
        customers = _all(
            db,
            """
            SELECT customer_id, company_name
            FROM prism_data.customers
            ORDER BY company_name
            """,
        )

        products = _all(
            db,
            """
            SELECT p.product_id, p.sku, p.product_name, p.customer_id,
                   c.company_name AS customer_name, p.storage_requirement, p.unit
            FROM prism_data.products p
            JOIN prism_data.customers c ON c.customer_id = p.customer_id
            ORDER BY p.product_name
            """,
        )

        locations = _all(
            db,
            """
            SELECT sl.location_id, sl.location_type, sl.capacity_units,
                   sl.occupied_units,
                   GREATEST(
                       sl.capacity_units - sl.occupied_units, 0
                   )::bigint AS remaining_capacity_units,
                   sl.status, a.customer_id AS area_customer_id,
                   sg.segment_name, z.zone_name, a.area_name
            FROM prism_data.storage_locations sl
            JOIN prism_data.segments sg ON sg.segment_id = sl.segment_id
            JOIN prism_data.zones z ON z.zone_id = sg.zone_id
            JOIN prism_data.areas a ON a.area_id = z.area_id
            ORDER BY a.area_name, z.zone_name, sl.location_id
            """,
        )

        workers = _all(
            db,
            """
            SELECT worker_id, name, role, skill, shift
            FROM prism_data.workers
            WHERE LOWER(status) = 'active'
              AND LOWER(attendance_status) = 'present'
            ORDER BY name
            """,
        )

        return {
            "customers": customers,
            "products": products,
            "locations": locations,
            "workers": workers,
        }

    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Could not load return options. Check the PRISM dataset tables.",
        ) from exc


@router.post("/returns")
def record_return(
    payload: ReturnRequest,
    db: Session = Depends(get_db),
):
    """Record a return and atomically apply its inventory disposition."""

    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=422, detail="Return reason cannot be blank.")

    if payload.disposition == "Restock" and payload.inspection_result != "Passed":
        raise HTTPException(
            status_code=422,
            detail="Restocking is permitted only after a Passed inspection.",
        )

    needs_location = payload.disposition != "Dispose"

    if needs_location and not payload.location_id:
        raise HTTPException(
            status_code=422,
            detail="A storage location is required for this disposition.",
        )

    return_id = f"RET-OP-{uuid.uuid4().hex[:12].upper()}"
    movement_id = f"MOV-RET-{uuid.uuid4().hex[:12].upper()}"

    try:
        # Check whether this request has already been completed.
        prior = _one(
            db,
            """
            SELECT operation_type, response_json
            FROM prism_app.operation_requests
            WHERE request_key = :request_key
            """,
            {"request_key": payload.request_key},
        )

        if prior:
            if prior["operation_type"] != "RETURN_PROCESSING":
                raise HTTPException(
                    status_code=409,
                    detail="This request key was already used for another operation.",
                )

            if prior.get("response_json"):
                db.rollback()
                return {
                    **prior["response_json"],
                    "idempotent_replay": True,
                }

            raise HTTPException(
                status_code=409,
                detail="This return request is already being processed. Retry shortly.",
            )

        claimed = _one(
            db,
            """
            INSERT INTO prism_app.operation_requests
                (request_key, operation_type, response_json)
            VALUES
                (:request_key, 'RETURN_PROCESSING', CAST('{}' AS jsonb))
            ON CONFLICT (request_key) DO NOTHING
            RETURNING request_key
            """,
            {"request_key": payload.request_key},
        )

        if not claimed:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="This request was submitted concurrently. Retry with a new request key.",
            )

        product = _one(
            db,
            """
            SELECT product_id, customer_id, product_name, storage_requirement
            FROM prism_data.products
            WHERE product_id = :product_id
            FOR SHARE
            """,
            {"product_id": payload.product_id},
        )

        if not product:
            raise HTTPException(status_code=404, detail="Product not found.")

        if product["customer_id"] != payload.customer_id:
            raise HTTPException(
                status_code=422,
                detail="The selected product does not belong to the selected customer.",
            )

        worker = _one(
            db,
            """
            SELECT worker_id, name
            FROM prism_data.workers
            WHERE worker_id = :worker_id
              AND LOWER(status) = 'active'
              AND LOWER(attendance_status) = 'present'
            FOR SHARE
            """,
            {"worker_id": payload.worker_id},
        )

        if not worker:
            raise HTTPException(
                status_code=422,
                detail="Select an active worker marked present.",
            )

        location = None

        if needs_location:
            location = _one(
                db,
                """
                SELECT sl.location_id, sl.location_type, sl.capacity_units,
                       sl.occupied_units, sl.status,
                       a.customer_id AS area_customer_id
                FROM prism_data.storage_locations sl
                JOIN prism_data.segments sg ON sg.segment_id = sl.segment_id
                JOIN prism_data.zones z ON z.zone_id = sg.zone_id
                JOIN prism_data.areas a ON a.area_id = z.area_id
                WHERE sl.location_id = :location_id
                FOR UPDATE OF sl
                """,
                {"location_id": payload.location_id},
            )

            if not location:
                raise HTTPException(status_code=404, detail="Storage location not found.")

            if str(location["area_customer_id"]) != str(payload.customer_id):
                raise HTTPException(
                    status_code=422,
                    detail="The selected location is not assigned to this customer.",
                )

            if str(location["status"] or "").strip().upper() not in {
                "ACTIVE",
                "AVAILABLE",
                "OCCUPIED",
                "PARTIAL",
            }:
                raise HTTPException(
                    status_code=422,
                    detail="The selected location is not available for storage.",
                )

            if not _storage_compatible(
                product["storage_requirement"],
                location["location_type"],
            ):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "The selected location does not match the product's "
                        "storage requirement. Use a compatible location."
                    ),
                )

            remaining = int(location["capacity_units"]) - int(
                location["occupied_units"] or 0
            )

            if payload.quantity > remaining:
                raise HTTPException(
                    status_code=422,
                    detail=f"Insufficient location capacity. Remaining units: {max(remaining, 0)}.",
                )

        # Claiming the request and all business changes share this transaction.
        db.execute(
            text(
                """
                INSERT INTO prism_data.returns_damage
                    (return_id, customer_id, product_id, quantity, reason,
                     damage_type, received_date, inspection_result,
                     disposition, status)
                VALUES
                    (:return_id, :customer_id, :product_id, :quantity, :reason,
                     :damage_type, CURRENT_DATE, :inspection_result,
                     :disposition, 'Processed')
                """
            ),
            {
                "return_id": return_id,
                "customer_id": payload.customer_id,
                "product_id": payload.product_id,
                "quantity": payload.quantity,
                "reason": reason,
                "damage_type": payload.damage_type.strip() or "None",
                "inspection_result": payload.inspection_result,
                "disposition": payload.disposition,
            },
        )

        if needs_location:
            inventory = _one(
                db,
                """
                SELECT inventory_id, batch_no, serial_tracking_type
                FROM prism_data.inventory
                WHERE product_id = :product_id
                  AND location_id = :location_id
                ORDER BY inventory_id
                LIMIT 1
                FOR UPDATE
                """,
                {
                    "product_id": payload.product_id,
                    "location_id": payload.location_id,
                },
            )

            available_add = payload.quantity if payload.disposition == "Restock" else 0
            quarantine_add = payload.quantity if payload.disposition == "Quarantine" else 0
            damaged_add = payload.quantity if payload.disposition == "Damaged" else 0

            if inventory:
                db.execute(
                    text(
                        """
                        UPDATE prism_data.inventory
                        SET quantity_available =
                                COALESCE(quantity_available, 0) + :available_add,
                            quantity_quarantined =
                                COALESCE(quantity_quarantined, 0) + :quarantine_add,
                            quantity_damaged =
                                COALESCE(quantity_damaged, 0) + :damaged_add,
                            last_updated = CURRENT_DATE
                        WHERE inventory_id = :inventory_id
                        """
                    ),
                    {
                        "available_add": available_add,
                        "quarantine_add": quarantine_add,
                        "damaged_add": damaged_add,
                        "inventory_id": inventory["inventory_id"],
                    },
                )
                inventory_id = inventory["inventory_id"]
            else:
                inventory_id = f"INV-RET-{uuid.uuid4().hex[:12].upper()}"

                db.execute(
                    text(
                        """
                        INSERT INTO prism_data.inventory
                            (inventory_id, product_id, location_id, batch_no,
                             serial_tracking_type, quantity_available,
                             quantity_reserved, quantity_damaged,
                             quantity_quarantined, last_updated)
                        VALUES
                            (:inventory_id, :product_id, :location_id, :batch_no,
                             'Batch', :available_add, 0, :damaged_add,
                             :quarantine_add, CURRENT_DATE)
                        """
                    ),
                    {
                        "inventory_id": inventory_id,
                        "product_id": payload.product_id,
                        "location_id": payload.location_id,
                        "batch_no": f"RETURN-{return_id}",
                        "available_add": available_add,
                        "damaged_add": damaged_add,
                        "quarantine_add": quarantine_add,
                    },
                )

            db.execute(
                text(
                    """
                    UPDATE prism_data.storage_locations
                    SET occupied_units = COALESCE(occupied_units, 0) + :quantity
                    WHERE location_id = :location_id
                    """
                ),
                {
                    "quantity": payload.quantity,
                    "location_id": payload.location_id,
                },
            )

            # A return receipt creates a movement record into the selected location.
            db.execute(
                text(
                    """
                    INSERT INTO prism_data.movements
                        (movement_id, product_id, from_location, to_location,
                         quantity, movement_type, timestamp, worker_id, reason)
                    VALUES
                        (:movement_id, :product_id, NULL, :to_location,
                         :quantity, :movement_type, CURRENT_DATE, :worker_id, :reason)
                    """
                ),
                {
                    "movement_id": movement_id,
                    "product_id": payload.product_id,
                    "to_location": payload.location_id,
                    "quantity": payload.quantity,
                    "movement_type": f"RETURN_{payload.disposition.upper()}",
                    "worker_id": payload.worker_id,
                    "reason": f"Return {return_id}: {reason}",
                },
            )
        else:
            inventory_id = None

        _record_activity(
            db,
            worker_id=payload.worker_id,
            return_id=return_id,
            product_id=payload.product_id,
            quantity=payload.quantity,
            disposition=payload.disposition,
        )

        db.execute(
            text(
                """
                INSERT INTO prism_app.audit_events
                    (event_type, actor_label, entity_type, entity_id, details_json)
                VALUES
                    ('RETURN_PROCESSED', :actor_label, 'return', :entity_id,
                     CAST(:details AS jsonb))
                """
            ),
            {
                "actor_label": worker["name"],
                "entity_id": return_id,
                "details": json.dumps(
                    {
                        "customer_id": payload.customer_id,
                        "product_id": payload.product_id,
                        "quantity": payload.quantity,
                        "inspection_result": payload.inspection_result,
                        "disposition": payload.disposition,
                        "location_id": payload.location_id,
                        "inventory_id": inventory_id,
                        "movement_id": movement_id if needs_location else None,
                    }
                ),
            },
        )

        response = {
            "success": True,
            "return_id": return_id,
            "product_id": payload.product_id,
            "quantity": payload.quantity,
            "disposition": payload.disposition,
            "inventory_id": inventory_id,
            "movement_id": movement_id if needs_location else None,
            "idempotent_replay": False,
        }

        db.execute(
            text(
                """
                UPDATE prism_app.operation_requests
                SET response_json = CAST(:response_json AS jsonb),
                    completed_at = CURRENT_TIMESTAMP
                WHERE request_key = :request_key
                """
            ),
            {
                "response_json": json.dumps(response),
                "request_key": payload.request_key,
            },
        )

        db.commit()
        return response

    except HTTPException:
        db.rollback()
        raise

    except SQLAlchemyError as exc:
        original_error = getattr(exc, "orig", exc)

        print(
            f"\n[PRISM RETURNS DATABASE ERROR] "
            f"{type(original_error).__name__}: {original_error}\n",
            flush=True,
        )

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=(
                "The return could not be saved. "
                "The database transaction was rolled back. "
                "Check the backend terminal for the underlying database error."
            ),
        ) from exc