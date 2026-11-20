import asyncio
from fastapi import FastAPI,Response
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.db import engine
from sqlalchemy import text
from redis.asyncio import Redis
from app.auth import router as auth_router
from app.google_oauth_routes import router as google_oauth_router
from app.integration_readiness import router as integration_readiness_router
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
from app.revenue_routes import router as revenue_router
from app.billing_routes import router as billing_router
from app.billing_dodo import router as billing_dodo_router
from app.notification_routes import router as notification_router
from app.rbac_routes import router as rbac_router
from app.social_oauth_routes import router as social_oauth_router
from app.admin_routes import router as admin_router
from app.middleware import RequestObservabilityMiddleware
from contextlib import asynccontextmanager
from app.config import production_problems
@asynccontextmanager
async def lifespan(_app):
 problems=production_problems(settings)
 if problems:raise RuntimeError("Refusing to start in production; fix: "+", ".join(problems))
 yield
app=FastAPI(title=settings.app_name,version="0.7.0",docs_url="/docs" if not settings.is_production else None,redoc_url=None,openapi_url="/openapi.json" if not settings.is_production else None,lifespan=lifespan)
app.add_middleware(RequestObservabilityMiddleware)
app.add_middleware(CORSMiddleware,allow_origins=settings.allowed_origins,allow_credentials=True,allow_methods=["GET","POST","PUT","PATCH","DELETE"],allow_headers=["Authorization","Content-Type","X-Request-ID"])
for r in [auth_router,google_oauth_router,integration_readiness_router,youtube_router,analytics_router,creator_features_router,research_router,intelligence_router,workflow_router,competitor_momentum_router,calendar_router,trend_history_router,publishing_queue_router,thumbnail_experiment_router,monetization_router,revenue_router,billing_router,billing_dodo_router,notification_router,rbac_router,social_oauth_router,admin_router]:app.include_router(r)
@app.get("/health",tags=["health"])
async def health():return {"status":"ok","service":"api","version":"0.6.0"}
@app.get("/ready",tags=["health"])
async def ready(response:Response):
 checks={"database":"error","redis":"error"}
 try:
  async with asyncio.timeout(3):
   async with engine.connect() as c:await c.execute(text("SELECT 1"))
  checks["database"]="ok"
 except Exception:checks["database"]="error"
 redis=None
 try:
  async with asyncio.timeout(3):redis=Redis.from_url(settings.redis_url,decode_responses=True);await redis.ping();checks["redis"]="ok"
 except Exception:checks["redis"]="error"
 finally:
  if redis:
   try:await redis.aclose()
   except Exception:pass
 if any(v!="ok" for v in checks.values()):response.status_code=503
 return {"status":"ok" if response.status_code==200 else "degraded","checks":checks}
