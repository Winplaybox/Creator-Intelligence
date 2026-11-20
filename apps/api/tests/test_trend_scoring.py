from datetime import datetime, timezone
from app.trend_scoring import score_video_signal, rank_video_signals

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)

def test_recent_high_engagement_scores_above_old_low_engagement():
    recent = {"published_at":"2026-11-20T11:00:00Z","views":10000,"likes":900,"comments":100}
    old = {"published_at":"2026-11-01T12:00:00Z","views":10000,"likes":10,"comments":5}
    assert score_video_signal(recent, NOW)["score"] > score_video_signal(old, NOW)["score"]

def test_missing_date_is_safe_and_returns_unknown_age():
    score = score_video_signal({"views":100,"likes":2,"comments":1}, NOW)
    assert score["age_hours"] is None
    assert score["label"] in {"high_signal","medium_signal","low_signal"}

def test_rank_is_descending_by_signal():
    low = {"video_id":"low","published_at":"2026-11-01T12:00:00Z","views":1000,"likes":1,"comments":0}
    high = {"video_id":"high","published_at":"2026-11-20T11:00:00Z","views":10000,"likes":900,"comments":100}
    ranked = rank_video_signals([low, high], NOW)
    assert ranked[0]["video_id"] == "high"
