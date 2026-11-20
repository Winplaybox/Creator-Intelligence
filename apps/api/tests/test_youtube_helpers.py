from app.services.youtube import pkce_pair
import base64,hashlib

def test_pkce_verifier_and_challenge():
 verifier,challenge=pkce_pair()
 expected=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
 assert challenge==expected
 assert len(verifier)>=43
