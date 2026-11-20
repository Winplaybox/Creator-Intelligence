import hashlib,secrets
from datetime import datetime,timedelta,timezone
from uuid import UUID
import jwt
from pwdlib import PasswordHash
from app.config import settings
password_hash=PasswordHash.recommended()
def hash_password(password:str)->str: return password_hash.hash(password)
def verify_password(password:str,encoded:str)->bool: return password_hash.verify(password,encoded)
def hash_refresh_token(token:str)->str: return hashlib.sha256(token.encode()).hexdigest()
def new_refresh_token()->str: return secrets.token_urlsafe(48)
def create_access_token(user_id:UUID)->tuple[str,int]:
 ttl=settings.jwt_access_minutes*60; now=datetime.now(timezone.utc)
 payload={"sub":str(user_id),"iss":settings.jwt_issuer,"iat":now,"exp":now+timedelta(seconds=ttl),"jti":secrets.token_urlsafe(16)}
 return jwt.encode(payload,settings.jwt_secret,algorithm="HS256"),ttl
def decode_access_token(token:str)->UUID:
 payload=jwt.decode(token,settings.jwt_secret,algorithms=["HS256"],issuer=settings.jwt_issuer,options={"require":["sub","exp","iss"]})
 return UUID(payload["sub"])
