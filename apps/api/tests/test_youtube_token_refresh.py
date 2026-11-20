from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
import pytest
from app.services import youtube


class FakeDB:
    committed = False
    async def commit(self):
        self.committed = True


@pytest.fixture
def fernet_key(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setattr(youtube.settings, "youtube_token_encryption_key", Fernet.generate_key().decode())


@pytest.mark.asyncio
async def test_valid_access_token_does_not_refresh(fernet_key):
    db = FakeDB()
    channel = SimpleNamespace(
        access_token_encrypted=youtube.encrypt_token("access"),
        refresh_token_encrypted=youtube.encrypt_token("refresh"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    token = await youtube.get_valid_access_token(db, channel)
    assert token == "access"
    assert db.committed is False


@pytest.mark.asyncio
async def test_expired_token_refreshes_and_persists(fernet_key, monkeypatch):
    db = FakeDB()
    channel = SimpleNamespace(
        access_token_encrypted=youtube.encrypt_token("old-access"),
        refresh_token_encrypted=youtube.encrypt_token("refresh"),
        token_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        updated_at=None,
    )
    async def fake_refresh(refresh_token):
        assert refresh_token == "refresh"
        return {"access_token": "new-access", "expires_in": 1800}
    monkeypatch.setattr(youtube, "refresh_access_token", fake_refresh)
    token = await youtube.get_valid_access_token(db, channel)
    assert token == "new-access"
    assert youtube.decrypt_token(channel.access_token_encrypted) == "new-access"
    assert channel.token_expires_at > datetime.now(timezone.utc)
    assert db.committed is True


@pytest.mark.asyncio
async def test_expired_token_without_refresh_token_requires_reconnect(fernet_key):
    db = FakeDB()
    channel = SimpleNamespace(
        access_token_encrypted=youtube.encrypt_token("old-access"),
        refresh_token_encrypted=None,
        token_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    with pytest.raises(RuntimeError, match="reconnect"):
        await youtube.get_valid_access_token(db, channel)
