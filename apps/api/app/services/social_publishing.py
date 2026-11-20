"""Provider publishing adapters for Facebook Pages and Instagram Business.

Called by a publishing worker. Credentials are supplied by the caller; this module
does not persist tokens or queue records.
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass
from typing import Any
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

    async def _wait_for_video_container(
        self, container_id: str, token: str, *, poll_interval: float = 3.0, timeout: float = 90.0
    ) -> None:
        """Wait for Instagram Reels processing; fail on error or bounded timeout."""
        elapsed = 0.0
        while elapsed <= timeout:
            status = await self._get(f"{container_id}?fields=status_code,status", token)
            code = str(status.get("status_code", "")).upper()
            if code == "FINISHED":
                return
            if code in {"ERROR", "EXPIRED"}:
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
        if not image_url.startswith("https://"):
            raise PublishingError("Instagram media URL must be HTTPS")
        container = await self._post(f"{instagram_id}/media", page_token, {
            "image_url": image_url, "caption": caption,
        })
        published = await self._post(f"{instagram_id}/media_publish", page_token, {
            "creation_id": str(container["id"]),
        })
        return PublishResult("instagram", str(published["id"]))

    async def publish_instagram_reel(self, instagram_id: str, page_token: str, *,
                                    video_url: str, caption: str = "",
                                    share_to_feed: bool = True) -> PublishResult:
        if not instagram_id or not page_token:
            raise PublishingError("Instagram account and Page token are required")
        if not video_url.startswith("https://"):
            raise PublishingError("Instagram video URL must be HTTPS")
        container = await self._post(f"{instagram_id}/media", page_token, {
            "media_type": "REELS", "video_url": video_url,
            "caption": caption, "share_to_feed": str(share_to_feed).lower(),
        })
        await self._wait_for_video_container(str(container["id"]), page_token)
        published = await self._post(f"{instagram_id}/media_publish", page_token, {
            "creation_id": str(container["id"]),
        })
        return PublishResult("instagram", str(published["id"]))
