"""Configuration-only readiness endpoint. It never exposes credentials or activates integrations."""
from fastapi import APIRouter
from app.config import settings
router = APIRouter(prefix="/v1/integrations", tags=["integration-readiness"])

def configured(*values: str) -> bool:
    return all(bool(v and v.strip()) for v in values)

@router.get("/readiness")
async def integration_readiness():
    checks = {
        "google_login": configured(settings.google_client_id, settings.google_client_secret, settings.google_oauth_redirect_uri),
        "youtube_oauth": configured(settings.google_client_id, settings.google_client_secret, settings.google_youtube_redirect_uri, settings.youtube_token_encryption_key),
        "meta_oauth": configured(settings.meta_client_id, settings.meta_client_secret, settings.meta_oauth_redirect_uri, settings.social_token_encryption_key),
        "dodo_live": configured(settings.dodo_api_key, settings.dodo_webhook_secret, settings.dodo_live_mode) and settings.dodo_live_mode.lower() == "true",
    }
    return {"configured": checks, "ready": {name: value for name, value in checks.items()}, "all_ready": all(checks.values())}
