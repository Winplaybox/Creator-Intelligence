"""Deterministic trend signal scoring; explicitly heuristic, not a prediction."""
from datetime import datetime, timezone
from typing import Any

def score_video_signal(video: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    published = video.get("published_at")
    try:
        age_hours = max(0.0, (now - datetime.fromisoformat(published.replace("Z", "+00:00"))).total_seconds() / 3600)
    except (AttributeError, TypeError, ValueError):
        age_hours = None
    views = max(0, int(video.get("views") or 0))
    likes = max(0, int(video.get("likes") or 0))
    comments = max(0, int(video.get("comments") or 0))
    engagement = ((likes + comments) / views * 100) if views else 0.0
    # Log-scaled views/hour prevent large channels from overwhelming the signal.
    velocity = views / max(age_hours or 24.0, 1.0)
    velocity_score = min(40.0, (velocity ** 0.5) * 2.0)
    engagement_score = min(30.0, engagement * 3.0)
    recency_score = 30.0 if age_hours is not None and age_hours <= 24 else 22.0 if age_hours is not None and age_hours <= 72 else 12.0 if age_hours is not None and age_hours <= 168 else 4.0
    total = round(velocity_score + engagement_score + recency_score, 2)
    return {
        "score": total,
        "components": {"velocity": round(velocity_score, 2), "engagement": round(engagement_score, 2), "recency": recency_score},
        "age_hours": round(age_hours, 2) if age_hours is not None else None,
        "views_per_hour": round(velocity, 2),
        "engagement_pct": round(engagement, 3),
        "label": "high_signal" if total >= 65 else "medium_signal" if total >= 35 else "low_signal",
        "disclaimer": "Heuristic signal based on public views, engagement and upload age; not a forecast of virality."
    }

def rank_video_signals(videos: list[dict[str, Any]], now: datetime | None = None) -> list[dict[str, Any]]:
    scored = []
    for video in videos:
        scored.append({**video, "trend_signal": score_video_signal(video, now)})
    return sorted(scored, key=lambda item: item["trend_signal"]["score"], reverse=True)
