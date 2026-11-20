import pytest
from app.services.youtube_upload import validate_video_metadata, YouTubeUploadError


def test_video_metadata_defaults_to_private():
    value = validate_video_metadata({"title": "Example"})
    assert value["snippet"]["title"] == "Example"
    assert value["status"]["privacyStatus"] == "private"
    assert value["status"]["selfDeclaredMadeForKids"] is False


def test_video_metadata_preserves_description_tags_and_privacy():
    value = validate_video_metadata({
        "title": "A short video",
        "description": "Description",
        "tags": ["shorts", "science"],
        "privacy_status": "unlisted",
        "category_id": "27",
        "made_for_kids": True,
    })
    assert value["snippet"]["tags"] == ["shorts", "science"]
    assert value["snippet"]["categoryId"] == "27"
    assert value["status"]["privacyStatus"] == "unlisted"
    assert value["status"]["selfDeclaredMadeForKids"] is True


@pytest.mark.parametrize("metadata", [
    {},
    {"title": " "},
    {"title": "x" * 101},
    {"title": "ok", "description": "x" * 5001},
    {"title": "ok", "tags": "not a list"},
    {"title": "ok", "tags": [1]},
    {"title": "ok", "privacy_status": "scheduled"},
    {"title": "ok", "category_id": "abc"},
])
def test_video_metadata_rejects_invalid_values(metadata):
    with pytest.raises(YouTubeUploadError):
        validate_video_metadata(metadata)
