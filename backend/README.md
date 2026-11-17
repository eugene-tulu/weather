# Weather Leverage API

FastAPI proxy in front of the [Dynamical point API](https://dynamical.org/api/) with a DuckDB response cache, inbound/outbound rate limiting, upstream retries, and a circuit breaker.

## Setup (conda env `ndvi`)

The checkout intentionally has no `.venv`. Use the conda environment named `ndvi`:

```bash
conda activate ndvi

pip install "fastapi>=0.115" "duckdb>=1.3.1" "httpx>=0.28.1" \
  "pydantic>=2.11.7" "uvicorn>=0.32" "sqlalchemy[asyncio]>=2" \
  "aiosqlite>=0.20" "asyncpg>=0.29" "redis>=5" "mcp>=1.30,<2" \
  "prometheus-client>=0.20" "sentry-sdk>=2" \
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
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/app.db` | Tenant, site, usage, forecast-sample, and observation store. |
| `REDIS_URL` | empty | Enables the shared Redis rate limiter when set. |
| `ADMIN_TOKEN` | empty | Enables `/admin` and its API when set. |
| `MCP_CACHE_DB_PATH` | `mcp-cache.duckdb` | Cache used by the MCP process. |
| `MCP_PORT` | `8001` | MCP streamable HTTP port. |
| `MCP_METRICS_PORT` | `9091` | Prometheus metrics port for the MCP process. |
| `QUOTA_DEFAULT` | `100000` | Default monthly quota for new organizations. |
| `DECISION_PRODUCTS` | `noaa-gfs-forecast,noaa-gefs-forecast-35-day` | Products used by the decision engine. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | empty | Enables OTLP tracing. |
| `SENTRY_DSN` | empty | Enables Sentry error tracking. |

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health/live` | Liveness. |
| `GET` | `/health/ready` | Readiness (DuckDB ping). |
| `GET` | `/metrics` | JSON counters. |
| `GET` | `/prometheus/metrics` | Prometheus metrics. |
| `GET` | `/admin` | Simple admin console (requires `ADMIN_TOKEN`). |
| `POST` | `/mcp` | MCP streamable HTTP endpoint. |
| `GET` | `/v1/sites` | List sites for the API key's organization. |
| `POST` | `/v1/sites` | Create a site. |
| `GET` | `/v1/sites/{id}/calibration` | Forecast/observation calibration report. |
| `POST` | `/v1/sites/{id}/forecast` | Decision forecast. |
| `POST` | `/v1/sites/{id}/workability` | Ranked workability windows. |
| `POST` | `/v1/sites/{id}/risk` | Weather risk flags. |
| `GET` | `/v1/usage` | Monthly usage and quota. |
| `GET` | `/api/runs` | Forecast runs (`dataProductId`, `limit`). |
| `GET` | `/api/geocode` | City search (`q`). |
| `GET` | `/api/product/{product_id}` | Product metadata. |
| `GET` | `/api/map-product/{product_id}` | Map-optimized virtual dataset options (Icechunk href + surface variables) from the STAC catalog. |
| `POST` | `/api/point` | Batch forecast queries. |
| `POST` | `/api/analysis` | Batch analysis queries (max 31 days). |

### Surface variables

The point API accepts `temperature_2m`, `precipitation_surface`, `total_cloud_cover_atmosphere`, `relative_humidity_2m`, `pressure_surface`, `wind_u_10m`, and `wind_v_10m`. `wind_speed` is derived in the frontend from the u/v components. Availability differs by product; the frontend filters unsupported models per variable. `boundary_layer_height` is not part of the point products and is only available in the map-optimized virtual datasets.

### Request validation

- Latitude `-90..90`, longitude `-180..180`.
- 1–10 products, 1–25 variables, no duplicates.
- Products and variables are checked against an allowlist matching the UI.
- `maxLeadTimeHours` is `1..840`.
- Timestamps must include a timezone offset.
- Analysis `endTime > startTime` and `endTime - startTime <= 31 days`.

## Organizations, API keys, and quotas

`/v1` and MCP tools require an API key (`X-API-Key` or `Authorization: Bearer`). Create an organization and key from `/admin` or:

```bash
curl -X POST https://$DOMAIN/admin/api/orgs \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -H "content-type: application/json" \
  -d '{"name":"Acme","monthly_quota":100000}'

curl -X POST https://$DOMAIN/admin/api/orgs/<org_id>/keys \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -H "content-type: application/json" \
  -d '{"name":"agent"}'
```

Usage is recorded per authenticated request/tool. `429` responses include `X-Quota-Limit`, `X-Quota-Remaining`, and `Retry-After`.

## MCP tools

The MCP server exposes `list_sites`, `get_site`, `forecast_site`, `workability_window`, `risk_flags`, `get_usage`, `get_operations`, and `get_data_provenance`. All tools require an API key and return confidence plus provenance. Run it separately:

```bash
MCP_PORT=8001 python mcp_server.py
```

## Calibration harness

When decisions run, forecast medians are stored in `forecast_samples`. Observations are posted to `/v1/sites/{id}/observations`; `/v1/sites/{id}/calibration` joins them and returns MAE, RMSE, bias, Brier score, and reliability bins. A standalone CSV harness is also available:

```bash
python calibration.py path/to/forecast-observations.csv --threshold 10
```

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

- Postgres stores tenants, API keys, sites, usage, forecast samples, and observations. Back it up with `./scripts/backup.sh`; restore with `./scripts/restore.sh <file>`.
- The DuckDB volume is `backend_data:/data` and is only a response cache; it can be rebuilt.
- `/health/ready` checks DuckDB and Postgres.
- `/metrics` exposes JSON counters; `/prometheus/metrics` is scraped by the optional Prometheus/Grafana stack (`docker-compose.observability.yml`).
- Traces go to an OTLP endpoint when `OTEL_EXPORTER_OTLP_ENDPOINT` is set; errors go to Sentry when `SENTRY_DSN` is set.
- `docker-compose.staging.yml` overlays the base stack for staging.
- `loadtest/k6.js` provides a smoke load test (`VUS`, `DURATION`, `BASE_URL`, `API_KEY`).
- Logs are structured JSON with a request ID, method, path, status, and duration.

## Data

Data is read from the Dynamical point API. Model licenses and attribution are listed in the [catalog](https://dynamical.org/catalog/). Do not redistribute data without checking the relevant license.