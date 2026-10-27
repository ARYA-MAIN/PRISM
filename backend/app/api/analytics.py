from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(
    prefix="/api/analytics",
    tags=["PRISM Analytics"],
)


def fetch_one(db: Session, query: str) -> dict:
    return dict(db.execute(text(query)).mappings().one())


def fetch_all(db: Session, query: str) -> list[dict]:
    return [dict(row) for row in db.execute(text(query)).mappings().all()]


def as_float(value) -> float:
    return round(float(value or 0), 2)


@router.get("/overview")
def analytics_overview(db: Session = Depends(get_db)):
    # Overall operational dataset counts
    counts = {}
    tables = [
        "warehouses", "customers", "areas", "zones", "segments",
        "storage_locations", "products", "workers", "inventory",
        "certifications", "orders", "inbound_transactions",
        "outbound_transactions", "movements", "returns_damage",
        "activity_log",
    ]

    for table in tables:
        counts[table] = db.execute(
            text(f'SELECT COUNT(*) FROM prism_data."{table}"')
        ).scalar_one()

    # Inventory health
    inventory = fetch_one(db, """
        SELECT
            COALESCE(SUM(quantity_available), 0)::bigint AS available_units,
            COALESCE(SUM(quantity_reserved), 0)::bigint AS reserved_units,
            COALESCE(SUM(quantity_damaged), 0)::bigint AS damaged_units,
            COALESCE(SUM(quantity_quarantined), 0)::bigint AS quarantined_units,
            COUNT(*)::int AS inventory_records,
            COUNT(DISTINCT product_id)::int AS products_in_stock
        FROM prism_data.inventory
    """)

    # Location-level space utilization; avoids adding parent and child capacities.
    capacity = fetch_one(db, """
        SELECT
            COALESCE(SUM(capacity_units), 0)::bigint AS total_capacity_units,
            COALESCE(SUM(occupied_units), 0)::bigint AS occupied_units,
            COUNT(*)::int AS total_locations,
            COUNT(*) FILTER (
                WHERE occupied_units = 0
            )::int AS empty_locations,
            COUNT(*) FILTER (
                WHERE capacity_units > 0
                  AND occupied_units >= capacity_units
            )::int AS full_locations
        FROM prism_data.storage_locations
    """)

    total_capacity = int(capacity["total_capacity_units"] or 0)
    occupied = int(capacity["occupied_units"] or 0)

    capacity["utilization_pct"] = (
        round(occupied / total_capacity * 100, 2)
        if total_capacity > 0 else None
    )
    capacity["remaining_capacity_units"] = max(
        total_capacity - occupied, 0
    )

    # Customer-area utilization, using the dataset's recorded KPI.
    areas = fetch_all(db, """
        SELECT
            a.area_id,
            a.area_name,
            c.company_name,
            a.area_sqft,
            a.capacity_units,
            a.utilization_pct,
            a.area_status
        FROM prism_data.areas a
        JOIN prism_data.customers c
          ON c.customer_id = a.customer_id
        ORDER BY a.area_name
    """)

    area_utilization = (
        round(
            sum(float(a["utilization_pct"] or 0) for a in areas)
            / len(areas),
            2,
        )
        if areas else None
    )

    # Inbound throughput and damaged-receipt rate.
    inbound = fetch_one(db, """
        SELECT
            COUNT(*)::int AS shipments_received,
            COALESCE(SUM(expected_qty), 0)::bigint AS expected_units,
            COALESCE(SUM(received_qty), 0)::bigint AS received_units,
            COALESCE(SUM(damaged_qty), 0)::bigint AS damaged_units,
            ROUND(
                COALESCE(
                    SUM(damaged_qty)::numeric
                    / NULLIF(SUM(received_qty), 0) * 100,
                    0
                ), 2
            )::float AS damage_rate_pct
        FROM prism_data.inbound_transactions
    """)

    # Outbound picking, packing, dispatch and order-to-dispatch time.
    outbound = fetch_one(db, """
        SELECT
            COUNT(*)::int AS outbound_records,
            COUNT(*) FILTER (
                WHERE dispatch_datetime IS NOT NULL
            )::int AS dispatched_records,
            COALESCE(SUM(requested_qty), 0)::bigint AS requested_units,
            COALESCE(SUM(picked_qty), 0)::bigint AS picked_units,
            COALESCE(SUM(packed_qty), 0)::bigint AS packed_units,
            ROUND(
                COALESCE(
                    SUM(picked_qty)::numeric
                    / NULLIF(SUM(requested_qty), 0) * 100,
                    0
                ), 2
            )::float AS pick_rate_pct,
            ROUND(
                COALESCE(
                    SUM(packed_qty)::numeric
                    / NULLIF(SUM(requested_qty), 0) * 100,
                    0
                ), 2
            )::float AS pack_rate_pct,
            ROUND(
                AVG(
                    EXTRACT(EPOCH FROM (
                        ot.dispatch_datetime - o.order_date
                    )) / 3600
                ) FILTER (
                    WHERE ot.dispatch_datetime IS NOT NULL
                      AND ot.dispatch_datetime >= o.order_date
                )::numeric,
                2
            )::float AS avg_order_to_dispatch_hours
        FROM prism_data.outbound_transactions ot
        JOIN prism_data.orders o ON o.order_id = ot.order_id
    """)

    order_statuses = fetch_all(db, """
        SELECT status, COUNT(*)::int AS order_count
        FROM prism_data.orders
        GROUP BY status
        ORDER BY order_count DESC, status
    """)

    delivery_statuses = fetch_all(db, """
        SELECT delivery_status, COUNT(*)::int AS record_count
        FROM prism_data.outbound_transactions
        GROUP BY delivery_status
        ORDER BY record_count DESC, delivery_status
    """)

    # Certification expiry and verification risks.
    certifications = fetch_one(db, """
        SELECT
            COUNT(*)::int AS total_certificates,
            COUNT(*) FILTER (
                WHERE expiry_date < CURRENT_DATE
            )::int AS expired_certificates,
            COUNT(*) FILTER (
                WHERE expiry_date >= CURRENT_DATE
                  AND expiry_date <= CURRENT_DATE + 30
            )::int AS expiring_within_30_days,
            COUNT(*) FILTER (
                WHERE LOWER(TRIM(verification_status))
                    IN ('failed', 'invalid', 'rejected')
            )::int AS failed_verification
        FROM prism_data.certifications
    """)

    # Workforce and activity overview. Activity counts are not productivity scores.
    workforce = fetch_one(db, """
        SELECT
            COUNT(*)::int AS total_workers,
            COUNT(*) FILTER (
                WHERE LOWER(TRIM(status)) = 'active'
            )::int AS active_workers
        FROM prism_data.workers
    """)

    attendance = fetch_all(db, """
        SELECT attendance_status, COUNT(*)::int AS worker_count
        FROM prism_data.workers
        GROUP BY attendance_status
        ORDER BY worker_count DESC, attendance_status
    """)

    activity = fetch_one(db, """
        SELECT
            COUNT(*)::int AS total_activity_events,
            MAX(timestamp) AS latest_activity_at
        FROM prism_data.activity_log
    """)

    # Explain metrics the current schema cannot reliably calculate.
    limitations = [
        {
            "metric": "Inventory accuracy",
            "reason": "No physical-count quantity is available for comparison."
        },
        {
            "metric": "Worker productivity per shift",
            "reason": "Activity events do not reliably establish units or tasks completed per shift."
        },
        {
            "metric": "Daily or weekly throughput trends",
            "reason": "A time-series endpoint is needed to group transactions by date."
        },
    ]

    return {
        "status": "success",
        "dataset": {
            "schema": "prism_data",
            "table_count": len(counts),
            "total_rows": sum(counts.values()),
            "row_counts": counts,
        },
        "inventory": inventory,
        "space_utilization": {
            "basis": "storage_locations",
            "warehouse_location_capacity": capacity,
            "average_recorded_area_utilization_pct": area_utilization,
            "areas": areas,
        },
        "inbound": inbound,
        "outbound": outbound,
        "orders": {
            "total_orders": counts["orders"],
            "status_breakdown": order_statuses,
        },
        "delivery_status_breakdown": delivery_statuses,
        "compliance": certifications,
        "workforce": {
            **workforce,
            "attendance_breakdown": attendance,
        },
        "activity": activity,
        "limitations": limitations,
    }

@router.get("/alerts")
def operational_alerts(db: Session = Depends(get_db)):
    alerts = []

    def add_alert(priority, category, title, description, evidence, action):
        alerts.append({
            "priority": priority,
            "category": category,
            "title": title,
            "description": description,
            "evidence": evidence,
            "suggested_action": action,
            "requires_human_review": True,
        })

    # 1. Products where available + reserved stock is below open demand.
    shortages = db.execute(text("""
        SELECT
            p.product_id,
            p.product_name,
            COALESCE(SUM(i.quantity_available), 0)::bigint AS available_units,
            COALESCE(SUM(i.quantity_reserved), 0)::bigint AS reserved_units,
            COALESCE(d.open_order_units, 0)::bigint AS open_order_units,
            GREATEST(
                COALESCE(d.open_order_units, 0)
                - COALESCE(SUM(i.quantity_available), 0)
                - COALESCE(SUM(i.quantity_reserved), 0),
                0
            )::bigint AS shortage_units
        FROM prism_data.products p
        LEFT JOIN prism_data.inventory i
            ON i.product_id = p.product_id
        LEFT JOIN (
            SELECT product_id, SUM(quantity)::bigint AS open_order_units
            FROM prism_data.orders
            WHERE LOWER(TRIM(status)) IN ('pending', 'processing')
            GROUP BY product_id
        ) d ON d.product_id = p.product_id
        GROUP BY p.product_id, p.product_name, d.open_order_units
        HAVING
            COALESCE(SUM(i.quantity_available), 0)
            + COALESCE(SUM(i.quantity_reserved), 0)
            < COALESCE(d.open_order_units, 0)
        ORDER BY shortage_units DESC
        LIMIT 50
    """)).mappings().all()

    for row in shortages:
        add_alert(
            "HIGH",
            "INVENTORY",
            f"Potential stock shortage: {row['product_name']}",
            "Recorded available and reserved stock is below the quantity "
            "on pending and processing orders.",
            dict(row),
            "Review open orders, confirm reservations, and plan replenishment "
            "or an approved stock allocation.",
        )

    # 2. Storage locations at capacity.
    full_locations = db.execute(text("""
        SELECT location_id, capacity_units, occupied_units, status
        FROM prism_data.storage_locations
        WHERE capacity_units > 0
          AND occupied_units >= capacity_units
        ORDER BY location_id
    """)).mappings().all()

    for row in full_locations:
        add_alert(
            "HIGH",
            "CAPACITY",
            f"Storage location full: {row['location_id']}",
            "The recorded occupied units have reached location capacity.",
            dict(row),
            "Review nearby compatible locations before assigning additional stock.",
        )

    # 3. Expired or soon-to-expire certifications.
    certificates = db.execute(text("""
        SELECT
            cert_id, owner_type, customer_id, product_id,
            certificate_type, certificate_no, expiry_date,
            verification_status
        FROM prism_data.certifications
        WHERE expiry_date <= CURRENT_DATE + 30
           OR LOWER(TRIM(verification_status))
              IN ('failed', 'invalid', 'rejected')
        ORDER BY expiry_date
    """)).mappings().all()

    for row in certificates:
        record = dict(row)
        expired = row["expiry_date"] < db.execute(
            text("SELECT CURRENT_DATE")
        ).scalar_one()
        failed = str(row["verification_status"]).strip().lower() in {
            "failed", "invalid", "rejected"
        }

        if expired:
            priority = "CRITICAL"
            title = f"Expired certificate: {row['certificate_no']}"
            action = "Verify the certificate and arrange renewal or escalation "
            "before relying on the affected product or operation."
        elif failed:
            priority = "HIGH"
            title = f"Certificate verification issue: {row['certificate_no']}"
            action = "Review the verification result and confirm compliance status."
        else:
            priority = "MEDIUM"
            title = f"Certificate expiring soon: {row['certificate_no']}"
            action = "Contact the certificate owner and schedule renewal."

        add_alert(
            priority,
            "COMPLIANCE",
            title,
            f"Certificate {row['certificate_type']} needs review.",
            record,
            action,
        )

    # 4. Delayed shipments and records requiring review.
    delivery_issues = db.execute(text("""
        SELECT delivery_status, COUNT(*)::int AS record_count
        FROM prism_data.outbound_transactions
        WHERE LOWER(TRIM(delivery_status))
              IN ('delayed', 'review required')
        GROUP BY delivery_status
        ORDER BY delivery_status
    """)).mappings().all()

    for row in delivery_issues:
        delayed = str(row["delivery_status"]).strip().lower() == "delayed"
        add_alert(
            "HIGH" if delayed else "MEDIUM",
            "OUTBOUND",
            f"Outbound records: {row['delivery_status']}",
            f"{row['record_count']} records currently carry this delivery status.",
            dict(row),
            "Review affected orders, dispatch details, and the latest delivery status.",
        )

    # 5. Low recorded storage utilization.
    capacity = db.execute(text("""
        SELECT
            COALESCE(SUM(capacity_units), 0)::bigint AS capacity_units,
            COALESCE(SUM(occupied_units), 0)::bigint AS occupied_units
        FROM prism_data.storage_locations
    """)).mappings().one()

    capacity_units = int(capacity["capacity_units"])
    occupied_units = int(capacity["occupied_units"])
    utilization = (
        round(occupied_units / capacity_units * 100, 2)
        if capacity_units > 0 else None
    )

    # Starter rule threshold; this is a configurable heuristic, not an AI prediction.
    if utilization is not None and utilization < 20:
        add_alert(
            "MEDIUM",
            "CAPACITY",
            "Low recorded space utilization",
            "Location occupancy is below the initial 20% review threshold.",
            {
                "occupied_units": occupied_units,
                "capacity_units": capacity_units,
                "utilization_pct": utilization,
                "review_threshold_pct": 20,
            },
            "Review the occupancy data and consider whether space can be "
            "consolidated without violating customer allocation or storage rules.",
        )

    # 6. Damaged and quarantined inventory needs operational review.
    stock_condition = db.execute(text("""
        SELECT
            COALESCE(SUM(quantity_damaged), 0)::bigint AS damaged_units,
            COALESCE(SUM(quantity_quarantined), 0)::bigint AS quarantined_units
        FROM prism_data.inventory
    """)).mappings().one()

    damaged_units = int(stock_condition["damaged_units"])
    quarantined_units = int(stock_condition["quarantined_units"])

    if damaged_units > 0 or quarantined_units > 0:
        add_alert(
            "MEDIUM",
            "INVENTORY",
            "Damaged or quarantined stock present",
            "Some inventory is marked damaged or quarantined and may require review.",
            {
                "damaged_units": damaged_units,
                "quarantined_units": quarantined_units,
            },
            "Review inspection and disposition records before returning affected "
            "stock to available inventory.",
        )

    priority_order = {
        "CRITICAL": 0,
        "HIGH": 1,
        "MEDIUM": 2,
        "LOW": 3,
    }
    alerts.sort(key=lambda item: priority_order[item["priority"]])

    priority_counts = {
        priority: sum(1 for alert in alerts if alert["priority"] == priority)
        for priority in priority_order
    }

    return {
        "status": "success",
        "alert_count": len(alerts),
        "priority_counts": priority_counts,
        "rule_based": True,
        "note": (
            "These are preliminary rule-based alerts. Validate stock reservation "
            "semantics and source records before acting on recommendations."
        ),
        "alerts": alerts,
    }
