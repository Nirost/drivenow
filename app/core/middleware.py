"""HTTP middleware: correlation IDs and request metrics."""

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.metrics import http_request_duration_seconds, http_requests_total
from app.core.request_context import set_request_id


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Assigns each request a correlation ID (honouring an inbound
    X-Request-ID from an upstream proxy) and echoes it back in the
    response headers so clients can quote it in bug reports.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        set_request_id(request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception:
            status = 500
            raise
        finally:
            # Label by route template ("/cars/{car_id}"), never the raw
            # path — labelling by raw path makes car_id a label value and
            # explodes cardinality in Prometheus.
            route = request.scope.get("route")
            endpoint = getattr(route, "path", request.url.path)
            elapsed = time.perf_counter() - start
            labels = (request.method, endpoint, str(status))
            http_request_duration_seconds.labels(*labels).observe(elapsed)
            http_requests_total.labels(*labels).inc()
        return response
