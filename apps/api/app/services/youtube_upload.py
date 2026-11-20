"""Resumable YouTube Data API upload primitive.

This module is worker-side only; it does not expose an upload endpoint or
activate publishing by itself.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

YOUTUBE_UPLOAD_INIT = "https://www.googleapis.com/upload/youtube/v3/videos"
CHUNK_SIZE = 8 * 1024 * 1024  # divisible by Google's 256 KiB resumable chunk unit


class YouTubeUploadError(RuntimeError):
    """Upload failed or provider rejected the request."""


def validate_video_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    title = str(metadata.get("title", "")).strip()
    if not title or len(title) > 100:
        raise YouTubeUploadError("Video title is required and must be at most 100 characters")
    description = str(metadata.get("description", ""))
    if len(description) > 5000:
        raise YouTubeUploadError("Video description must be at most 5000 characters")
    tags = metadata.get("tags", [])
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
        raise YouTubeUploadError("Tags must be a list of strings")
    if len(tags) > 500 or any(len(tag) > 100 for tag in tags):
        raise YouTubeUploadError("Tags exceed provider limits")
    privacy = str(metadata.get("privacy_status", "private")).lower()
    if privacy not in {"private", "unlisted", "public"}:
        raise YouTubeUploadError("Invalid privacy status")
    category_id = str(metadata.get("category_id", "22"))
    if not category_id.isdigit():
        raise YouTubeUploadError("Category ID must be numeric")
    return {
        "snippet": {"title": title, "description": description, "tags": tags, "categoryId": category_id},
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": bool(metadata.get("made_for_kids", False))},
    }


def _validate_session_url(url: str) -> None:
    parsed = httpx.URL(url)
    if parsed.scheme != "https" or parsed.host is None or not parsed.host.endswith("googleapis.com"):
        raise YouTubeUploadError("Provider returned an invalid resumable upload URL")


async def resumable_upload(
    access_token: str,
    file_path: str | Path,
    metadata: dict[str, Any],
    *,
    timeout: float = 120.0,
    chunk_size: int = CHUNK_SIZE,
) -> dict[str, Any]:
    """Upload a local file using bounded chunked PUTs and Google's resumable protocol.

    The caller owns token refresh, queue leases, quota, retries across process
    restarts, and persisting the provider video ID. This helper never buffers the
    entire video in memory.
    """
    path = Path(file_path)
    if not access_token:
        raise YouTubeUploadError("YouTube access token is required")
    if not path.is_file():
        raise YouTubeUploadError("Upload file does not exist")
    size = path.stat().st_size
    if size <= 0:
        raise YouTubeUploadError("Upload file is empty")
    if chunk_size <= 0 or chunk_size % (256 * 1024) != 0:
        raise YouTubeUploadError("Chunk size must be a positive multiple of 256 KiB")
    body = validate_video_metadata(metadata)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Type": "video/*",
        "X-Upload-Content-Length": str(size),
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            init = await client.post(
                YOUTUBE_UPLOAD_INIT,
                params={"part": "snippet,status", "uploadType": "resumable"},
                headers=headers,
                content=json.dumps(body),
            )
            init.raise_for_status()
            upload_url = init.headers.get("Location")
            if not upload_url:
                raise YouTubeUploadError("Provider did not return a resumable upload URL")
            _validate_session_url(upload_url)

            result: dict[str, Any] | None = None
            offset = 0
            with path.open("rb") as source:
                while offset < size:
                    chunk = source.read(min(chunk_size, size - offset))
                    if not chunk:
                        raise YouTubeUploadError("Video file ended before the declared size")
                    end = offset + len(chunk) - 1
                    chunk_headers = {
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "video/*",
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {offset}-{end}/{size}",
                    }
                    response = await client.put(upload_url, headers=chunk_headers, content=chunk)
                    if response.status_code in (200, 201):
                        result = response.json()
                        offset = end + 1
                        break
                    if response.status_code == 308:
                        # The server's Range header indicates the last persisted byte.
                        persisted = response.headers.get("Range")
                        if persisted and persisted.startswith("bytes=0-"):
                            try:
                                acknowledged = int(persisted.split("-", 1)[1]) + 1
                            except ValueError as exc:
                                raise YouTubeUploadError("YouTube returned an invalid upload Range") from exc
                            if acknowledged <= offset or acknowledged > end + 1:
                                raise YouTubeUploadError("YouTube returned an unexpected upload offset")
                            offset = acknowledged
                            source.seek(offset)
                            continue
                        # No Range means no bytes persisted; retry the same chunk once
                        # is intentionally avoided here to prevent an infinite loop.
                        raise YouTubeUploadError("YouTube did not acknowledge the uploaded chunk")
                    response.raise_for_status()
                    raise YouTubeUploadError("Unexpected response from YouTube resumable upload")
            if not isinstance(result, dict) or not result.get("id"):
                raise YouTubeUploadError("YouTube returned no video ID")
            return result
    except YouTubeUploadError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise YouTubeUploadError("YouTube resumable upload failed") from exc
