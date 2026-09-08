# ---- build stage --------------------------------------------------------
# uv ships as a static binary in this image; nothing else is needed to
# resolve and install dependencies.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies are installed in their own layer, keyed only on the
# manifest and lockfile. Application code changes therefore do NOT
# invalidate the dependency layer — rebuilds after a code edit are
# near-instant.
#
# --frozen fails the build if uv.lock is missing or out of sync with
# pyproject.toml, so an image can never be built from an unpinned
# dependency set.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev

# ---- runtime stage ------------------------------------------------------
# Plain Python base: uv itself is a build-time tool and is not shipped.
FROM python:3.12-slim

RUN useradd --create-home --uid 1000 appuser

WORKDIR /app

# Only the resolved virtualenv crosses the stage boundary — no uv, no
# build cache, no compiler.
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --chown=appuser:appuser . .

RUN mkdir -p /app/logs && chown appuser:appuser /app/logs

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health/live').status==200 else 1)"

# Default command; docker-compose overrides it per service
# (api / relay / notifications / migrate).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
