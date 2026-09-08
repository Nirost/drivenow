"""
Database engine, session lifecycle, and the Unit of Work.

Design note — transaction ownership:
Repositories deliberately do NOT commit. A repository has no idea whether
it is the whole business operation or one step of five, so it cannot know
where a transaction ends. Repositories `flush()` (to get generated PKs
and surface constraint violations early); the *service* opens a
UnitOfWork and commits exactly once, atomically, when the operation
succeeds.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine, autocommit=False, autoflush=False, future=True
)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


class UnitOfWork:
    """
    Transaction boundary for a single business operation.

    Usage:
        with self.uow:
            rental = self.rental_repo.create(...)
            self.car_repo.set_status(car, CarStatus.IN_USE)
        # committed here, atomically — or rolled back if the body raised

    Nesting is supported and only the outermost block commits, so a
    service method that calls another service method does not commit
    half of the caller's work.
    """

    def __init__(self, session: Session):
        self.session = session
        self._depth = 0

    def __enter__(self) -> "UnitOfWork":
        self._depth += 1
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self._depth -= 1
        if self._depth > 0:
            return False  # inner block: let the outermost one decide
        if exc_type is not None:
            self.session.rollback()
        else:
            self.session.commit()
        return False  # never suppress exceptions


def get_db():
    """
    FastAPI dependency yielding a session.

    Rolls back on any unhandled exception before closing. Without this,
    a failed request can leave a dirty session that a pooled connection
    later reuses.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
