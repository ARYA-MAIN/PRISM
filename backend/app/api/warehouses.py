
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.warehouse import Warehouse
from app.schemas.warehouse import WarehouseCreate, WarehouseResponse


router = APIRouter(
    prefix="/api/warehouses",
    tags=["Warehouses"],
)


@router.post("/", response_model=WarehouseResponse, status_code=201)
def create_warehouse(
    warehouse_data: WarehouseCreate,
    db: Session = Depends(get_db),
):
    warehouse = Warehouse(**warehouse_data.model_dump())
    db.add(warehouse)

    try:
        db.commit()
        db.refresh(warehouse)
        return warehouse
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not create warehouse. Check the server logs.",
        )


@router.get("/", response_model=list[WarehouseResponse])
def list_warehouses(db: Session = Depends(get_db)):
    return db.query(Warehouse).order_by(Warehouse.id).all()
