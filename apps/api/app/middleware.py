"""Request correlation and latency logging."""
import logging,time,uuid
from starlette.middleware.base import BaseHTTPMiddleware
log=logging.getLogger("creator.api")
class RequestObservabilityMiddleware(BaseHTTPMiddleware):
 async def dispatch(self,request,call_next):
  rid=request.headers.get("x-request-id") or uuid.uuid4().hex;start=time.perf_counter()
  response=await call_next(request);ms=round((time.perf_counter()-start)*1000,2);response.headers["X-Request-ID"]=rid
  log.info("request_id=%s method=%s path=%s status=%s duration_ms=%s",rid,request.method,request.url.path,response.status_code,ms)
  return response
