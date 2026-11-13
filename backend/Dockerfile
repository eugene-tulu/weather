FROM python:3.12-slim AS deps

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev

FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CACHE_DB_PATH=/data/cache.duckdb

WORKDIR /app

COPY --from=deps /app/.venv ./.venv
COPY app.py cache.py config.py main.py metrics.py rate_limit.py schemas.py upstream.py ./

RUN mkdir -p /data \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --create-home app \
    && chown -R app:app /app /data

USER app

EXPOSE 8000

CMD [".venv/bin/uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]