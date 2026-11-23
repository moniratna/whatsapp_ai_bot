from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.webhook import router as webhook_router
from app.api.dashboard import router as dashboard_router
from app.services.extractor import close_extractor_http_client
from app.services.openwa import openwa_service


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await close_extractor_http_client()
    await openwa_service.close()

app = FastAPI(title="WhatsApp Real Estate AI Bot", lifespan=lifespan)

app.include_router(webhook_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")


@app.get("/health")
def health_check():
    return {"status": "healthy"}
