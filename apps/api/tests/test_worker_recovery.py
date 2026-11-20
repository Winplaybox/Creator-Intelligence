from datetime import datetime,timezone,timedelta
from app.worker import CLAIM_TTL,is_stale_claim
def test_missing_claim_timestamp_is_stale():
 assert is_stale_claim({})
def test_recent_claim_is_not_stale():
 now=datetime.now(timezone.utc)
 assert not is_stale_claim({"worker_claimed_at":now.isoformat()},now)
def test_old_claim_is_stale():
 now=datetime.now(timezone.utc)
 old=now-CLAIM_TTL-timedelta(seconds=1)
 assert is_stale_claim({"worker_claimed_at":old.isoformat()},now)
def test_invalid_claim_timestamp_is_stale():
 assert is_stale_claim({"worker_claimed_at":"invalid"})
