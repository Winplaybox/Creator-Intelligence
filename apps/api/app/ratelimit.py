"""Small Redis fixed-window rate limiter for abuse-prone endpoints (auth, checkout)."""
import hashlib,logging
from fastapi import HTTPException,Request
from redis.asyncio import Redis
from app.config import settings
log=logging.getLogger("creator.ratelimit")
_redis:Redis|None=None
def _client()->Redis:
 global _redis
 if _redis is None:_redis=Redis.from_url(settings.redis_url,decode_responses=True,socket_timeout=2,socket_connect_timeout=2)
 return _redis
def client_ip(request:Request)->str:
 # Behind Caddy, X-Forwarded-For is overwritten with the real client address.
 xff=request.headers.get("x-forwarded-for","") if settings.trust_proxy else ""
 return (xff.split(",")[0].strip() if xff else (request.client.host if request.client else "unknown"))
async def limit(request:Request,bucket:str,max_hits:int,window_s:int,identity:str="")->None:
 key_src=f"{bucket}:{client_ip(request)}:{identity.lower()}"
 key="rl:"+hashlib.sha256(key_src.encode()).hexdigest()[:32]
 try:
  r=_client();n=await r.incr(key)
  if n==1:await r.expire(key,window_s)
 except Exception:
  if settings.is_production:
   log.error("rate limiter unavailable; rejecting %s",bucket);raise HTTPException(503,"Service temporarily unavailable")
  return
 if n>max_hits:raise HTTPException(429,"Too many attempts. Please try again later.",headers={"Retry-After":str(window_s)})
