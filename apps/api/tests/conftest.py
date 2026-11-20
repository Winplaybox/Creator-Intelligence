"""Configure integration settings before any app module is imported (settings/engine are module-level)."""
import base64
import os

if os.environ.get("INTEGRATION_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["INTEGRATION_DATABASE_URL"]
    os.environ["REDIS_URL"] = os.environ.get("INTEGRATION_REDIS_URL", "redis://127.0.0.1:6379/0")
    os.environ["GOOGLE_CLIENT_ID"] = "ci-test.apps.googleusercontent.com"
    os.environ["DODO_WEBHOOK_SECRET"] = "whsec_" + base64.b64encode(b"creator-intelligence-test-secret!").decode()
    os.environ["ADMIN_EMAILS"] = "boss@example.com"
    os.environ["DODO_PRODUCT_CREATOR_MONTHLY"] = "pdt_creator_m"
