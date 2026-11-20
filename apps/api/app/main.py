from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings

app = FastAPI(title=settings.app_name, version="0.1.0", docs_url="/docs" if settings.app_env != "production" else None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_credentials=True, allow_methods=["GET","POST","PUT","PATCH","DELETE"], allow_headers=["Authorization","Content-Type","X-Request-ID"])

@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "service": "api", "version": "0.1.0"}

@app.get("/ready", tags=["health"])
async def ready():
    # TODO: readiness must verify database and Redis connectivity before production.
    return {"status": "ready"}
