
from sqlalchemy import Integer, String, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Inventory(Base):
    __tablename__ = "inventory"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True
    )

    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id"),
        nullable=False,
        index=True,
    )

    sku: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )

    product_name: Mapped[str] = mapped_column(
        String(200), nullable=False
    )

    quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    reorder_level: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10
    )

    unit_price: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
