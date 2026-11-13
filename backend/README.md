# Weather Leverage API

FastAPI proxy in front of the [Dynamical point API](https://dynamical.org/api/) with a DuckDB response cache, inbound/outbound rate limiting, upstream retries, and a circuit breaker.

## Setup (conda env `ndvi`)

The checkout intentionally has no `.venv`. Use the conda environment named `ndvi`:

```bash
conda activate ndvi

pip install "fastapi>=0.115" "duckdb>=1.3.1" "httpx>=0.28.1" \
  "pydantic>=2.11.7" "uvicorn>=0.32" \
  "pytest>=8" "pytest-asyncio>=0.24" "respx>=0.21" "ruff>=0.6" "black>=24"
```

The Docker image builds its own isolated environment with `uv sync --frozen --no-dev`; that environment lives inside the image.

## Run

```bash
uvicorn main:app --reload --port 8000
```

Or run the container:

```bash
docker compose up backend
```

## Test and lint

```bash
pytest
ruff check .
black --check .
```

## Configuration

Copy `.env.example` to `.env` and adjust as needed. Environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated CORS origins. |
| `CACHE_DB_PATH` | `cache.duckdb` | DuckDB file. Use a writable volume in Docker. |
| `CACHE_TTL_SECONDS` | `600` | Cache TTL. |
| `CACHE_MAX_ROWS` | `10000` | LRU cap. |
| `RATE_LIMIT_PER_MINUTE` | `60` | Inbound per-IP limit. |
| `OUTBOUND_RATE_PER_10S` | `20` | Upstream budget per 10 seconds. |
| `OUTBOUND_RATE_PER_60S` | `250` | Upstream budget per 60 seconds. |
| `OUTBOUND_MAX_WAIT_SECONDS` | `5` | Wait for an outbound slot before returning 503. |
| `UPSTREAM_BASE` | `https://api.dynamical.org/v1` | API base. |
| `GEOCODE_URL` | `https://geocoding-api.open-meteo.com/v1/search` | Geocoding provider. |
| `UPSTREAM_TIMEOUT_SECONDS` | `60` | Read timeout. |
| `UPSTREAM_CONNECT_TIMEOUT_SECONDS` | `5` | Connect timeout. |
| `UPSTREAM_MAX_RETRIES` | `2` | Retry count for 429/503/5xx. |
| `UPSTREAM_FAILURE_THRESHOLD` | `5` | Failures before the circuit opens. |
| `UPSTREAM_OPEN_SECONDS` | `30` | Circuit open duration. |
| `TRUST_PROXY_HEADERS` | `true` | Parse `X-Forwarded-For`. Only enable behind a trusted proxy. |
| `ENVIRONMENT` | `production` | Environment name. |

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health/live` | Liveness. |
| `GET` | `/health/ready` | Readiness (DuckDB ping). |
| `GET` | `/metrics` | Counters. |
| `GET` | `/api/runs` | Forecast runs (`dataProductId`, `limit`). |
| `GET` | `/api/geocode` | City search (`q`). |
| `GET` | `/api/product/{product_id}` | Product metadata. |
| `POST` | `/api/point` | Batch forecast queries. |
| `POST` | `/api/analysis` | Batch analysis queries (max 31 days). |

### Request validation

- Latitude `-90..90`, longitude `-180..180`.
- 1–10 products, 1–25 variables, no duplicates.
- Products and variables are checked against an allowlist matching the UI.
- `maxLeadTimeHours` is `1..840`.
- Timestamps must include a timezone offset.
- Analysis `endTime > startTime` and `endTime - startTime <= 31 days`.

## Cache

The cache stores each successful upstream result as JSON in DuckDB. Entries expire after `CACHE_TTL_SECONDS`; expired rows are deleted on read, on a periodic task, and at startup. The table is capped at `CACHE_MAX_ROWS`; the oldest entries are removed first.

Concurrent identical misses are collapsed with a per-key `asyncio.Lock`, so only one request hits the upstream for the same key.

## Rate limiting and upstream protection

- Inbound: per-client-IP sliding window (`RATE_LIMIT_PER_MINUTE`), with `Retry-After` and `X-RateLimit-*` headers.
- Outbound: process-wide sliding window at `OUTBOUND_RATE_PER_10S` and `OUTBOUND_RATE_PER_60S`. Every upstream call waits for a slot, then times out with 503 if the wait exceeds `OUTBOUND_MAX_WAIT_SECONDS`.
- Retries: 429/503/5xx are retried up to `UPSTREAM_MAX_RETRIES` times with exponential backoff plus jitter and `Retry-After`.
- Circuit breaker: after `UPSTREAM_FAILURE_THRESHOLD` consecutive failures the upstream is marked open for `UPSTREAM_OPEN_SECONDS`; requests fail fast with 503.

The defaults are below the provider's documented 30 requests/10s edge limit and 300 forecast/analysis requests/60s worker limit. If you change `RATE_LIMIT_PER_MINUTE` or the number of products per request, keep the aggregate outbound traffic below those limits.

## Operations

- The DuckDB volume is `backend_data:/data` in `docker-compose.yml`. Back it up before upgrading.
- `/health/ready` returns 503 when DuckDB is unavailable; the container healthcheck uses `/health/live` for liveness and Compose uses it for restart decisions.
- `/metrics` exposes counters for requests, rate-limit rejections, cache hits/misses, upstream calls/errors/retries, outbound rejections, and circuit state.
- Logs are structured JSON with a request ID, method, path, status, and duration.

## Data

Data is read from the Dynamical point API. Model licenses and attribution are listed in the [catalog](https://dynamical.org/catalog/). Do not redistribute data without checking the relevant license.