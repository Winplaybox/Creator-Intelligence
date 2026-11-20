from app.integration_readiness import configured

def test_configured_requires_all_values():
    assert configured("id", "secret", "redirect")
    assert not configured("id", "", "redirect")
    assert not configured("", "", "")
