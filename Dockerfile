# syntax=docker/dockerfile:1

# Build stage: install the locked dependencies and the project into /app/.venv.
FROM python:3.15.0-slim-trixie AS builder
COPY --from=ghcr.io/astral-sh/uv:0.9.22 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
# Dependencies first, so a source change does not rebuild this layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY README.md LICENSE ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

# Runtime stage: the virtualenv only, run by a non-root user. Same base as the builder, so the
# venv's interpreter path exists here too.
FROM python:3.15.0-slim-trixie
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app \
    && mkdir /data \
    && chown app:app /data
COPY --from=builder --chown=app:app /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    BOOKS_DATA_DIR=/data
VOLUME /data
WORKDIR /data
USER app
# A batch CLI has no port to probe: the check proves the package imports and the entry point runs.
HEALTHCHECK --interval=30s --timeout=10s --retries=3 CMD ["books-scraping", "--version"]
ENTRYPOINT ["books-scraping"]
CMD ["run", "--limit", "20"]
