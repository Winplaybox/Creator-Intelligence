from app.security import hash_password,verify_password,hash_refresh_token,new_refresh_token
def test_password_hash_and_verification():
 encoded=hash_password("correct horse battery staple")
 assert encoded!="correct horse battery staple"
 assert verify_password("correct horse battery staple",encoded)
 assert not verify_password("incorrect",encoded)
def test_refresh_token_randomness_and_hash():
 token=new_refresh_token()
 assert token!=new_refresh_token()
 assert hash_refresh_token(token)!=token
 assert hash_refresh_token(token)==hash_refresh_token(token)
