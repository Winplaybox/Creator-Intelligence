from app.services.social_publishing import classify_container_status


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
