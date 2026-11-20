from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.db import engine
from sqlalchemy import text
from redis.asyncio import Redis
from app.auth import router as auth_router
from app.youtube_routes import router as youtube_router
from app.analytics_routes import router as analytics_router
from app.creator_features import router as creator_features_router
from app.research_routes import router as research_router
from app.intelligence_routes import router as intelligence_router
from app.workflow_routes import router as workflow_router
from app.competitor_momentum import router as competitor_momentum_router
from app.calendar_routes import router as calendar_router
from app.trend_history_routes import router as trend_history_router
from app.publishing_queue_routes import router as publishing_queue_router
from app.thumbnail_experiment_routes import router as thumbnail_experiment_router
from app.monetization_routes import router as monetization_router
app=FastAPI(title=settings.app_name,version="0.5.0",docs_url="/docs" if settings.app_env!="production" else None,redoc_url=None)
app.add_middleware(CORSMiddleware,allow_origins=settings.allowed_origins,allow_credentials=True,allow_methods=["GET","POST","PUT","PATCH","DELETE"],allow_headers=["Authorization","Content-Type","X-Request-ID"])
app.include_router(auth_router)
app.include_router(youtube_router)
app.include_router(analytics_router)
app.include_router(creator_features_router)
app.include_router(research_router)
app.include_router(intelligence_router)
app.include_router(workflow_router)
app.include_router(competitor_momentum_router)
app.include_router(calendar_router)
app.include_router(trend_history_router)
app.include_router(publishing_queue_router)
app.include_router(thumbnail_experiment_router)
app.include_router(monetization_router)
@app.get("/health",tags=["health"])
async def health(): return {"status":"ok","service":"api","version":"0.5.0"}
@app.get("/ready",tags=["health"])
async def ready(response: Response):
    checks = {"database": "unavailable", "redis": "unavailable"}
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await redis.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"
    finally:
        await redis.aclose()
    healthy = all(value == "ok" for value in checks.values())
    response.status_code = 200 if healthy else 503
    return {"status": "ready" if healthy else "not_ready", "checks": checks}
