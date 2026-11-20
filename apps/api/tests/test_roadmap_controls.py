import pytest
from app.services.roadmap_controls import (
    SubscriptionState, idempotency_fingerprint, notification_allowed,
    retry_delay_seconds, transition_subscription, validate_public_http_url,
)

def test_idempotency_is_stable_and_workspace_scoped():
    payload = {"title": "video", "tags": ["a", "b"]}
    assert idempotency_fingerprint("w1", "publish", payload) == idempotency_fingerprint("w1", "publish", payload)
    assert idempotency_fingerprint("w1", "publish", payload) != idempotency_fingerprint("w2", "publish", payload)

@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://localhost", "https://user:pass@example.com", "https://example.com:444"])
def test_url_rejects_unsafe_shapes(url):
    with pytest.raises(ValueError):
        validate_public_http_url(url)

def test_url_accepts_standard_public_shape_without_dns():
    assert validate_public_http_url("https://example.com/path") == "https://example.com/path"

def test_subscription_transition_rules():
    assert transition_subscription(SubscriptionState.TRIAL, SubscriptionState.ACTIVE) == SubscriptionState.ACTIVE
    with pytest.raises(ValueError):
        transition_subscription(SubscriptionState.EXPIRED, SubscriptionState.ACTIVE)

def test_retry_backoff_is_bounded():
    assert retry_delay_seconds(1) == 5
    assert retry_delay_seconds(5) == 80
    assert retry_delay_seconds(100) == 900

def test_notification_preferences_require_both_opt_ins():
    prefs = {"channels": {"email": True}, "categories": {"product": True}}
    assert notification_allowed(prefs, "email", "product")
    assert not notification_allowed(prefs, "email", "billing")
    assert not notification_allowed({**prefs, "unsubscribed": True}, "email", "product")
