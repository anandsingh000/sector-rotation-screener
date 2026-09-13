from fastapi import FastAPI
from backend.app.api.routes import router
from backend.app.core.config import settings
from backend.app.core.logging_config import configure_logging

configure_logging()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Sector rotation screener API",
)

app.include_router(router, prefix="/api/v1")

@app.get("/", tags=["system"])
def root():
    return {
        "app": settings.app_name,
        "status": "running",
        "docs": "/docs",
        "api": "/api/v1",
    }
