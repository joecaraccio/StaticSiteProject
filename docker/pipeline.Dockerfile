# The pipeline image: Python 3.12 + uv + DuckDB, and nothing else.
FROM python:3.12-slim

# uv is copied from its own distroless image rather than pip-installed, which is
# the method its docs recommend and keeps the layer small.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    DATA_ROOT=/data

WORKDIR /app

# Dependencies first, so editing pipeline code does not invalidate this layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project --no-dev

# Then the project itself, installed editable so a bind mount over /app/pipeline
# takes effect without a rebuild.
COPY pipeline ./pipeline
COPY tests ./tests
RUN uv sync --locked --no-dev

RUN mkdir -p /data && useradd --create-home --uid 1000 pipeline \
    && chown -R pipeline:pipeline /data /app
USER pipeline

ENTRYPOINT ["pipeline"]
CMD ["status"]
