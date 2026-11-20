"""Shared safety primitives for roadmap areas 27–35.

These helpers intentionally avoid provider calls and persistent state. Production callers
must back idempotency, rate limits, notification delivery, and usage ledgers with
transactional/distributed storage.
"""
from __future__ import annotations
import hashlib, json, ipaddress, socket
from enum import Enum
from urllib.parse import urlsplit

def idempotency_fingerprint(workspace_id: str, operation: str, payload: dict) -> str:
    """Stable SHA-256 fingerprint scoped to workspace and operation."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    raw = f"{workspace_id}:{operation}:{canonical}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def validate_public_http_url(url: str, *, resolve_dns: bool = False) -> str:
    """Reject unsafe URL shapes; DNS checks are advisory and must be repeated at connect time."""
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("URL must be absolute HTTP(S)")
    if parsed.username or parsed.password:
        raise ValueError("URL credentials are not allowed")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid URL port") from exc
    if port not in (None, 80, 443):
        raise ValueError("Only standard HTTP(S) ports are allowed")
    host = parsed.hostname.rstrip(".").lower()
    if host in ("localhost", "localhost.localdomain") or host.endswith(".localhost"):
        raise ValueError("Local hostnames are not allowed")
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            raise ValueError("Non-public IP addresses are not allowed")
    except ValueError as exc:
        if str(exc) == "Non-public IP addresses are not allowed":
            raise
        if resolve_dns:
            try:
                answers = socket.getaddrinfo(host, port or (443 if parsed.scheme == "https" else 80))
            except OSError as dns_exc:
                raise ValueError("Hostname could not be resolved") from dns_exc
            for answer in answers:
                address = ipaddress.ip_address(answer[4][0])
                if not address.is_global:
                    raise ValueError("Hostname resolves to a non-public IP")
    return url

class SubscriptionState(str, Enum):
    TRIAL = "trial"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    EXPIRED = "expired"

_ALLOWED_SUBSCRIPTION_TRANSITIONS = {
    SubscriptionState.TRIAL: {SubscriptionState.ACTIVE, SubscriptionState.CANCELED, SubscriptionState.EXPIRED},
    SubscriptionState.ACTIVE: {SubscriptionState.PAST_DUE, SubscriptionState.CANCELED, SubscriptionState.EXPIRED},
    SubscriptionState.PAST_DUE: {SubscriptionState.ACTIVE, SubscriptionState.CANCELED, SubscriptionState.EXPIRED},
    SubscriptionState.CANCELED: {SubscriptionState.EXPIRED, SubscriptionState.ACTIVE},
    SubscriptionState.EXPIRED: set(),
}
def transition_subscription(current: SubscriptionState, target: SubscriptionState) -> SubscriptionState:
    if target == current:
        return current
    if target not in _ALLOWED_SUBSCRIPTION_TRANSITIONS[current]:
        raise ValueError(f"Invalid subscription transition: {current.value} -> {target.value}")
    return target

def retry_delay_seconds(attempt: int, *, base: int = 5, cap: int = 900) -> int:
    if attempt < 1:
        raise ValueError("attempt must be >= 1")
    return min(cap, base * (2 ** min(attempt - 1, 20)))

def notification_allowed(preferences: dict, channel: str, category: str) -> bool:
    if preferences.get("unsubscribed", False):
        return False
    channels = preferences.get("channels", {})
    categories = preferences.get("categories", {})
    return bool(channels.get(channel, False) and categories.get(category, False))

def safe_request_id(value: str | None) -> str:
    """Normalize an incoming request id; never trust arbitrary header content."""
    if value and len(value) <= 64 and all(c.isalnum() or c in "-_." for c in value):
        return value
    return hashlib.sha256((value or "").encode()).hexdigest()[:24]
