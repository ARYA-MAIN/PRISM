
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Warehouse(Base):
    __tablename__ = "warehouses"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True
    )

    name: Mapped[str] = mapped_column(
        String(150), nullable=False
    )

    location: Mapped[str] = mapped_column(
        String(250), nullable=False
    )

    warehouse_type: Mapped[str] = mapped_column(
        String(100), nullable=False, default="General"
    )

    capacity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
