
from pydantic import BaseModel, ConfigDict, Field


class WarehouseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    location: str = Field(min_length=1, max_length=250)
    warehouse_type: str = Field(default="General", max_length=100)
    capacity: int = Field(default=0, ge=0)


class WarehouseResponse(WarehouseCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)
