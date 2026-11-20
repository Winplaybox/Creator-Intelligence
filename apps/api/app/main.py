from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.auth import router as auth_router
from app.youtube_routes import router as youtube_router
from app.analytics_routes import router as analytics_router
app=FastAPI(title=settings.app_name,version="0.3.0",docs_url="/docs" if settings.app_env!="production" else None,redoc_url=None)
app.add_middleware(CORSMiddleware,allow_origins=settings.allowed_origins,allow_credentials=True,allow_methods=["GET","POST","PUT","PATCH","DELETE"],allow_headers=["Authorization","Content-Type","X-Request-ID"])
app.include_router(auth_router)
app.include_router(youtube_router)
app.include_router(analytics_router)
@app.get("/health",tags=["health"])
async def health(): return {"status":"ok","service":"api","version":"0.3.0"}
@app.get("/ready",tags=["health"])
async def ready(): return {"status":"ready","checks":{"database":"not_yet_verified","redis":"not_yet_verified"}}
