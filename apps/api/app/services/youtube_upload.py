"""Resumable YouTube Data API upload primitive.

This module is a worker-side building block. It does not expose upload endpoints
or activate publishing by itself.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, AsyncIterator

import httpx

YOUTUBE_UPLOAD_INIT = "https://www.googleapis.com/upload/youtube/v3/videos"
CHUNK_SIZE = 8 * 1024 * 1024


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


async def _file_chunks(path: Path, chunk_size: int = CHUNK_SIZE) -> AsyncIterator[bytes]:
    with path.open("rb") as source:
        while True:
            chunk = source.read(chunk_size)
            if not chunk:
                break
            yield chunk


async def resumable_upload(
    access_token: str,
    file_path: str | Path,
    metadata: dict[str, Any],
    *,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Upload a local video using Google's resumable protocol.

    The caller is responsible for token refresh, quota accounting, queue leases,
    and persisting the returned provider video ID. File is streamed in bounded
    chunks; no full-file buffering is performed.
    """
    path = Path(file_path)
    if not access_token:
        raise YouTubeUploadError("YouTube access token is required")
    if not path.is_file():
        raise YouTubeUploadError("Upload file does not exist")
    size = path.stat().st_size
    if size <= 0:
        raise YouTubeUploadError("Upload file is empty")
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
            upload_headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "video/*",
                "Content-Length": str(size),
            }
            response = await client.put(upload_url, headers=upload_headers, content=_file_chunks(path))
            response.raise_for_status()
            result = response.json()
    except YouTubeUploadError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise YouTubeUploadError("YouTube resumable upload failed") from exc
    if not isinstance(result, dict) or not result.get("id"):
        raise YouTubeUploadError("YouTube returned no video ID")
    return result
