from app.services.social_publishing import classify_container_status, validate_media_url, PublishingError
import pytest


def test_instagram_container_finished_is_ready():
    assert classify_container_status("FINISHED") == "ready"


def test_instagram_container_error_is_failed():
    assert classify_container_status("ERROR") == "failed"


def test_instagram_container_expired_is_failed():
    assert classify_container_status("EXPIRED") == "failed"


def test_unknown_container_state_remains_pending():
    assert classify_container_status("IN_PROGRESS") == "pending"


def test_status_is_case_and_whitespace_tolerant():
    assert classify_container_status(" finished ") == "ready"


def test_missing_status_remains_pending():
    assert classify_container_status(None) == "pending"


@pytest.mark.parametrize("url", [
    "https://cdn.example.com/media/video.mp4",
    "https://media.example.org/image.jpg?sig=abc",
])
def test_validate_media_url_accepts_public_https(url):
    assert validate_media_url(url) == url


@pytest.mark.parametrize("url", [
    "http://cdn.example.com/media.mp4",
    "https://localhost/media.mp4",
    "https://127.0.0.1/media.mp4",
    "https://10.0.0.5/media.mp4",
    "https://169.254.169.254/latest/meta-data",
    "https://example.com:444/media.mp4",
    "https://user:pass@example.com/media.mp4",
    "https://example.com",
    "not-a-url",
])
def test_validate_media_url_rejects_unsafe_or_invalid_urls(url):
    with pytest.raises(PublishingError):
        validate_media_url(url)
