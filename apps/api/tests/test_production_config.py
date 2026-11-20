from app.config import Settings, production_problems


def test_development_has_no_gate():
    assert production_problems(Settings(app_env="development")) == []


def test_production_refuses_dev_defaults():
    problems = " ".join(production_problems(Settings(app_env="production", admin_emails="", google_client_id="",
        jwt_secret="dev-only-change-me-to-a-32-byte-random-secret", cookie_secure=False, cors_origins="http://localhost:3000",
        web_base_url="http://localhost:3000",
        database_url="postgresql+asyncpg://creator:creator_dev_password@localhost:5432/creator_intelligence")))
    for needle in ("JWT_SECRET", "COOKIE_SECURE", "DATABASE_URL", "CORS_ORIGINS", "WEB_BASE_URL", "ADMIN_EMAILS"):
        assert needle in problems


def test_production_ok_when_configured():
    s = Settings(app_env="production", jwt_secret="x" * 48, cookie_secure=True,
                 database_url="postgresql+asyncpg://creator:strong@postgres:5432/ci", cors_origins="https://creator.winplaybox.in",
                 web_base_url="https://creator.winplaybox.in", admin_emails="a@b.co", google_client_id="", dodo_api_key="",
                 dodo_webhook_secret="")
    assert production_problems(s) == []
    assert "DODO_WEBHOOK_SECRET" in " ".join(production_problems(s.model_copy(update={"dodo_api_key": "dodo_live_x"})))
