from app.api.datasets import router as datasets_router
from app.api.analytics import router as analytics_router
from app.api.workspace import router as workspace_router
from app.api.operations_workflows import router as operations_workflows_router
from app.api.order_fulfillment import router as order_fulfillment_router
from fastapi import FastAPI

from app.core.config import settings
from app.api.warehouses import router as warehouses_router

app = FastAPI(
    title=settings.app_name,
    description="Warehouse and Logistics Decision Support System",
    version=settings.app_version,
)

app.include_router(warehouses_router)
app.include_router(datasets_router)
app.include_router(analytics_router)
app.include_router(workspace_router)
app.include_router(operations_workflows_router)
app.include_router(order_fulfillment_router)

@app.get("/")
def root():
    return {
        "message": "PRISM backend is running",
        "status": "ok",
        "version": settings.app_version,
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}
