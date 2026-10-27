
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(
    prefix="/api/data",
    tags=["PRISM Dataset"],
)

# Only these predefined tables can be queried through this API.
ALLOWED_TABLES = {
    "warehouses",
    "customers",
    "areas",
    "zones",
    "segments",
    "storage_locations",
    "products",
    "workers",
    "inventory",
    "certifications",
    "orders",
    "inbound_transactions",
    "outbound_transactions",
    "movements",
    "returns_damage",
    "activity_log",
}


@router.get("/summary")
def dataset_summary(db: Session = Depends(get_db)):
    """Return row counts for all imported PRISM tables."""
    summary = {}

    for table in sorted(ALLOWED_TABLES):
        result = db.execute(
            text(f'SELECT COUNT(*) FROM prism_data."{table}"')
        )
        summary[table] = result.scalar_one()

    return {
        "status": "success",
        "schema": "prism_data",
        "tables": len(summary),
        "total_rows": sum(summary.values()),
        "row_counts": summary,
    }


@router.get("/{table_name}")
def get_dataset_table(
    table_name: str,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Return a paginated view of an allowed PRISM table."""
    if table_name not in ALLOWED_TABLES:
        raise HTTPException(
            status_code=404,
            detail="Dataset table not found.",
        )

    total = db.execute(
        text(f'SELECT COUNT(*) FROM prism_data."{table_name}"')
    ).scalar_one()

    result = db.execute(
        text(
            f'SELECT * FROM prism_data."{table_name}" '
            "LIMIT :limit OFFSET :offset"
        ),
        {"limit": limit, "offset": offset},
    )

    items = [dict(row) for row in result.mappings().all()]

    return {
        "status": "success",
        "table": table_name,
        "total_records": total,
        "limit": limit,
        "offset": offset,
        "returned_records": len(items),
        "items": items,
    }
