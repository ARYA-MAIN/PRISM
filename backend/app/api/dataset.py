from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(prefix="/api/dataset", tags=["Dataset APIs"])


def fetch_page(db, count_sql, data_sql, params):
    total = db.execute(text(count_sql), params).scalar_one()
    rows = db.execute(text(data_sql), params).mappings().all()
    return {
        "items": [dict(row) for row in rows],
        "total": total,
        "limit": params["limit"],
        "offset": params["offset"],
    }


@router.get("/warehouses")
def get_warehouses(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT warehouse_id, name, address, total_area_sqft,
               total_capacity_units, operating_hours,
               ownership_type, status
        FROM prism_data.warehouses
        ORDER BY warehouse_id
    """)).mappings().all()

    return {"items": [dict(row) for row in rows], "total": len(rows)}


@router.get("/products")
def get_products(
    q: str | None = Query(default=None, max_length=100),
    category: str | None = Query(default=None, max_length=100),
    customer_id: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    conditions = []
    params = {"limit": limit, "offset": offset}

    if q:
        conditions.append(
            "(p.product_name ILIKE :q OR p.sku ILIKE :q "
            "OR p.brand ILIKE :q)"
        )
        params["q"] = f"%{q}%"

    if category:
        conditions.append("p.category = :category")
        params["category"] = category

    if customer_id:
        conditions.append("p.customer_id = :customer_id")
        params["customer_id"] = customer_id

    where = " WHERE " + " AND ".join(conditions) if conditions else ""

    joins = """
        FROM prism_data.products p
        JOIN prism_data.customers c
          ON c.customer_id = p.customer_id
    """

    return fetch_page(
        db,
        "SELECT COUNT(*) " + joins + where,
        """
        SELECT p.product_id, p.sku, p.product_name, p.category,
               p.subcategory, p.brand, p.model, p.unit, p.weight_kg,
               p.storage_requirement, p.fragile_flag, p.customer_id,
               c.company_name
        """ + joins + where +
        " ORDER BY p.product_name LIMIT :limit OFFSET :offset",
        params,
    )


@router.get("/inventory")
def get_inventory(
    product_id: str | None = Query(default=None, max_length=100),
    location_id: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    conditions = []
    params = {"limit": limit, "offset": offset}

    if product_id:
        conditions.append("i.product_id = :product_id")
        params["product_id"] = product_id

    if location_id:
        conditions.append("i.location_id = :location_id")
        params["location_id"] = location_id

    where = " WHERE " + " AND ".join(conditions) if conditions else ""

    joins = """
        FROM prism_data.inventory i
        JOIN prism_data.products p ON p.product_id = i.product_id
        JOIN prism_data.storage_locations sl
          ON sl.location_id = i.location_id
        JOIN prism_data.segments sg ON sg.segment_id = sl.segment_id
        JOIN prism_data.zones z ON z.zone_id = sg.zone_id
        JOIN prism_data.areas a ON a.area_id = z.area_id
    """

    return fetch_page(
        db,
        "SELECT COUNT(*) " + joins + where,
        """
        SELECT i.inventory_id, i.product_id, p.product_name, p.sku,
               i.location_id, i.batch_no,
               i.quantity_available, i.quantity_reserved,
               i.quantity_damaged, i.quantity_quarantined,
               i.last_updated, sl.location_type, sl.status AS location_status,
               sl.capacity_units, sl.occupied_units,
               sg.segment_id, sg.segment_name,
               z.zone_id, z.zone_name, a.area_id, a.area_name
        """ + joins + where +
        " ORDER BY p.product_name LIMIT :limit OFFSET :offset",
        params,
    )


@router.get("/locations")
def get_locations(
    status: str | None = Query(default=None, max_length=50),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    conditions = []
    params = {"limit": limit, "offset": offset}

    if status:
        conditions.append("sl.status = :status")
        params["status"] = status

    where = " WHERE " + " AND ".join(conditions) if conditions else ""

    joins = """
        FROM prism_data.storage_locations sl
        JOIN prism_data.segments sg ON sg.segment_id = sl.segment_id
        JOIN prism_data.zones z ON z.zone_id = sg.zone_id
        JOIN prism_data.areas a ON a.area_id = z.area_id
    """

    return fetch_page(
        db,
        "SELECT COUNT(*) " + joins + where,
        """
        SELECT sl.location_id, sl.rack_no, sl.shelf_no, sl.bin_no,
               sl.location_type, sl.capacity_units, sl.occupied_units,
               sl.status, sg.segment_id, sg.segment_name,
               z.zone_id, z.zone_name, a.area_id, a.area_name
        """ + joins + where +
        " ORDER BY sl.location_id LIMIT :limit OFFSET :offset",
        params,
    )
