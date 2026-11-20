"""Redis-backed daily quota accounting with atomic reserve semantics."""
from redis.asyncio import Redis
from app.config import settings
from datetime import datetime,timezone
class YouTubeQuotaExceeded(RuntimeError): pass
class YouTubeQuota:
 def __init__(self,redis:Redis|None=None,limit:int|None=None):
  self.redis=redis or Redis.from_url(settings.redis_url,decode_responses=True)
  self.limit=limit or settings.youtube_daily_quota_limit
 async def reserve(self,units:int=1)->int:
  if units<=0: raise ValueError("units must be positive")
  day=datetime.now(timezone.utc).strftime("%Y-%m-%d")
  key=f"youtube:quota:{day}"
  lua="""
  local current=tonumber(redis.call('GET',KEYS[1]) or '0')
  local amount=tonumber(ARGV[1])
  local limit=tonumber(ARGV[2])
  if current+amount>limit then return -1 end
  local next=current+amount
  redis.call('SET',KEYS[1],next,'EX',ARGV[3])
  return next
  """
  result=await self.redis.eval(lua,1,key,units,self.limit,172800)
  if result<0: raise YouTubeQuotaExceeded("Daily YouTube API quota exhausted")
  return int(result)
 async def close(self):
  await self.redis.aclose()
