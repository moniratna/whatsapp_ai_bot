from fastapi import FastAPI

from app.api.webhook import router as webhook_router

app = FastAPI(title="WhatsApp Real Estate AI Bot")

app.include_router(webhook_router, prefix="/api/v1")


@app.get("/health")
def health_check():
    return {"status": "healthy"}
