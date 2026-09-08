"""
Exception-to-HTTP mapping — the single place that knows about status codes.

Routes stay free of try/except: they call the service and let domain
exceptions propagate. Adding a new domain error means adding one line
here, not editing every handler that might raise it.
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.logging_config import get_logger
from app.core.metrics import domain_errors_total
from app.services.exceptions import (
    ConflictError,
    DomainError,
    NotFoundError,
)

logger = get_logger(__name__)

# Most specific first is unnecessary here because we walk the MRO.
_STATUS_BY_TYPE: list[tuple[type[DomainError], int]] = [
    (NotFoundError, 404),
    (ConflictError, 409),
    (DomainError, 400),
]


def _status_for(exc: DomainError) -> int:
    for exc_type, status in _STATUS_BY_TYPE:
        if isinstance(exc, exc_type):
            return status
    return 400


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError):
        status = _status_for(exc)
        domain_errors_total.labels(code=exc.code).inc()
        logger.warning("domain_error code=%s status=%s: %s", exc.code, status, exc)
        return JSONResponse(
            status_code=status,
            content={"detail": str(exc), "code": exc.code},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception):
        # Log the stack trace, but never leak internals to the client.
        logger.exception("unhandled_error path=%s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "code": "internal_error"},
        )
