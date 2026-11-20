from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
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
async def ready(): return {"status":"ready","checks":{"database":"not_yet_verified","redis":"not_yet_verified"}}
