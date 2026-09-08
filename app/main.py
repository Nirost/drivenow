"""
Application entrypoint — wiring only.

Responsibilities: build the app, install middleware and error handlers,
mount routers, and run startup checks. No business logic.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.api.cars import router as cars_router
from app.api.errors import register_exception_handlers
from app.api.rentals import router as rentals_router
from app.api.system import router as system_router
from app.core.config import settings
from app.core.database import engine
from app.core.logging_config import get_logger, setup_logging
from app.core.middleware import MetricsMiddleware, RequestContextMiddleware

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is owned by Alembic migrations (`alembic upgrade head`),
    # not by create_all() — so the schema is versioned and reviewable.
    # We only verify connectivity here and fail fast if the DB is absent.
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    logger.info("startup.complete environment=%s", settings.environment)
    yield
    engine.dispose()
    logger.info("shutdown.complete")


app = FastAPI(
    title=settings.app_name,
    description="Vehicle management system for the DriveNow car rental company.",
    version="1.0.0",
    lifespan=lifespan,
)

# Order matters: request ID is set first so metrics and error logs carry it.
app.add_middleware(MetricsMiddleware)
app.add_middleware(RequestContextMiddleware)

register_exception_handlers(app)

app.include_router(cars_router)
app.include_router(rentals_router)
app.include_router(system_router)
