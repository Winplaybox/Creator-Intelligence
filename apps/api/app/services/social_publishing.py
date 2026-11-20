"""Provider publishing adapters for Facebook Pages and Instagram Business.

Called by a publishing worker. Credentials are supplied by the caller; this module
does not persist tokens or queue records.
"""
from __future__ import annotations

import asyncio
import ipaddress
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx


class PublishingError(RuntimeError):
    """Provider rejected a publish request or returned an invalid response."""


@dataclass(frozen=True)
class PublishResult:
    platform: str
    provider_post_id: str


def classify_container_status(status_code: str | None) -> str:
    code = (status_code or "").strip().upper()
    if code == "FINISHED":
        return "ready"
    if code in {"ERROR", "EXPIRED"}:
        return "failed"
    return "pending"


def validate_media_url(value: str) -> str:
    """Validate a provider-fetchable media URL and reject obvious SSRF targets.

    This is a defense-in-depth URL check; it cannot prevent DNS rebinding, so
    production media URLs should also be hosted on an application-controlled CDN.
    """
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        if parsed.scheme != "https" or not host or parsed.username or parsed.password:
            raise ValueError
        if parsed.port not in (None, 443):
            raise ValueError
        if host.lower() in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
            raise ValueError
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address and (address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_unspecified):
            raise ValueError
        if not parsed.path or parsed.path == "/":
            raise ValueError
    except (ValueError, TypeError):
        raise PublishingError("Media URL must be a valid public HTTPS URL") from None
    return value


class MetaPublisher:
    def __init__(self, graph_version: str = "v23.0", timeout: float = 30.0):
        self.base_url = f"https://graph.facebook.com/{graph_version}"
        self.timeout = timeout

    async def _post(self, endpoint: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
        params = dict(payload)
        params["access_token"] = token
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/{endpoint}", data=params)
                response.raise_for_status()
                result = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise PublishingError("Meta publishing request failed") from exc
        if not isinstance(result, dict) or not result.get("id"):
            raise PublishingError("Meta returned no publish identifier")
        return result

    async def _get(self, endpoint: str, token: str) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/{endpoint}", params={"access_token": token})
                response.raise_for_status()
                result = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise PublishingError("Meta media status request failed") from exc
        if not isinstance(result, dict):
            raise PublishingError("Meta returned an invalid media status")
        return result

    async def _wait_for_container(
        self, container_id: str, token: str, *, poll_interval: float = 3.0, timeout: float = 90.0
    ) -> None:
        """Wait for Instagram media processing; fail on terminal error or timeout."""
        elapsed = 0.0
        while elapsed <= timeout:
            status = await self._get(f"{container_id}?fields=status_code,status", token)
            classification = classify_container_status(status.get("status_code"))
            if classification == "ready":
                return
            if classification == "failed":
                raise PublishingError("Instagram media processing failed")
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        raise PublishingError("Instagram media processing timed out")

    async def publish_facebook_page(self, page_id: str, page_token: str, *,
                                   message: str, link: str | None = None) -> PublishResult:
        if not page_id or not page_token:
            raise PublishingError("Facebook Page and access token are required")
        if not message.strip() and not link:
            raise PublishingError("Facebook post must include text or a link")
        payload: dict[str, Any] = {"message": message}
        if link:
            payload["link"] = link
        result = await self._post(f"{page_id}/feed", page_token, payload)
        return PublishResult("facebook", str(result["id"]))

    async def publish_instagram_photo(self, instagram_id: str, page_token: str, *,
                                     image_url: str, caption: str = "") -> PublishResult:
        if not instagram_id or not page_token:
            raise PublishingError("Instagram account and Page token are required")
        image_url = validate_media_url(image_url)
        container = await self._post(f"{instagram_id}/media", page_token, {
            "image_url": image_url, "caption": caption,
        })
        await self._wait_for_container(str(container["id"]), page_token)
        published = await self._post(f"{instagram_id}/media_publish", page_token, {
            "creation_id": str(container["id"]),
        })
        return PublishResult("instagram", str(published["id"]))

    async def publish_instagram_reel(self, instagram_id: str, page_token: str, *,
                                    video_url: str, caption: str = "",
                                    share_to_feed: bool = True) -> PublishResult:
        if not instagram_id or not page_token:
            raise PublishingError("Instagram account and Page token are required")
        video_url = validate_media_url(video_url)
        container = await self._post(f"{instagram_id}/media", page_token, {
            "media_type": "REELS", "video_url": video_url,
            "caption": caption, "share_to_feed": str(share_to_feed).lower(),
        })
        await self._wait_for_container(str(container["id"]), page_token)
        published = await self._post(f"{instagram_id}/media_publish", page_token, {
            "creation_id": str(container["id"]),
        })
        return PublishResult("instagram", str(published["id"]))
