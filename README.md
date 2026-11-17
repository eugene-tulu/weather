# Disagreement

A weather-forecast explorer that shows **how much models disagree**, not just one deterministic answer. It combines NOAA GFS/HRRR/GEFS, ECMWF AIFS/IFS ENS, and DWD ICON-EU forecasts with analysis data through the [Dynamical point API](https://dynamical.org/api/).

The frontend is a Next.js 16 / React 19 / Recharts app. The backend is a FastAPI proxy with a DuckDB response cache, inbound and outbound rate limiting, upstream retries, and a circuit breaker.

## Quick start (Docker)

```bash
cp .env.example .env
# Set DOMAIN to a hostname you control (required for a publicly trusted TLS certificate),
# plus POSTGRES_PASSWORD and ADMIN_TOKEN.
docker compose up --build
```

Services: `postgres`, `redis`, `backend` (REST/decision/admin), `mcp` (streamable HTTP MCP), `frontend`, and `caddy`. The admin console is at `/admin`; the MCP endpoint is at `/mcp`; the REST decision API is under `/v1`.

Caddy terminates TLS and is the only service that publishes ports 80/443. The backend and frontend are reachable only on the internal Docker network. The frontend calls the backend same-origin at `/api`.

For local HTTPS with a self-signed certificate, set `DOMAIN=localhost` and accept Caddy's internal CA warning in the browser.

## Local development

### Backend (conda env `ndvi`)

The repository does **not** use a project-local `.venv`. Use the existing conda environment named `ndvi`:

```bash
conda activate ndvi
# or: conda run -n ndvi <command>

pip install "fastapi>=0.115" "duckdb>=1.3.1" "httpx>=0.28.1" \
  "pydantic>=2.11.7" "uvicorn>=0.32" \
  "pytest>=8" "pytest-asyncio>=0.24" "respx>=0.21" "ruff>=0.6" "black>=24"

cd backend
uvicorn main:app --reload --port 8000
pytest
```

`backend/.venv` was intentionally removed. The Docker image still uses `uv sync` to build its own isolated environment; that environment is inside the image, not the checkout.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

For local development against a separately running backend, set `NEXT_PUBLIC_API_BASE=http://localhost:8000` in `frontend/.env.local` (already present, ignored by git). In Docker, leave it empty so the browser uses the same-origin `/api` path proxied by Caddy.

## Environment

| Variable | Default | Purpose |
| --- | --- | --- |
| `DOMAIN` | `localhost` | Hostname for Caddy/TLS. |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated CORS origins for direct backend access. |
| `CACHE_DB_PATH` | `cache.duckdb` | DuckDB cache path. Docker uses `/data/cache.duckdb`. |
| `CACHE_TTL_SECONDS` | `600` | Response cache TTL. |
| `CACHE_MAX_ROWS` | `10000` | Maximum cache rows before LRU pruning. |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/app.db` | Tenant/site/usage/calibration database. Docker uses Postgres. |
| `REDIS_URL` | empty | Enables the shared Redis rate limiter. |
| `ADMIN_TOKEN` | empty | Enables `/admin`; set this in production. |
| `QUOTA_DEFAULT` | `100000` | Default monthly unit quota for new organizations. |
| `MCP_PORT` | `8001` | MCP streamable HTTP port. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | empty | Enables OTLP tracing. |
| `SENTRY_DSN` | empty | Enables Sentry error tracking. |
| `RATE_LIMIT_PER_MINUTE` | `60` | Inbound requests per client IP per minute. |
| `OUTBOUND_RATE_PER_10S` | `20` | Maximum upstream requests per 10 seconds. |
| `OUTBOUND_RATE_PER_60S` | `250` | Maximum upstream requests per 60 seconds. |
| `OUTBOUND_MAX_WAIT_SECONDS` | `5` | Maximum wait for an outbound slot before returning 503. |
| `UPSTREAM_BASE` | `https://api.dynamical.org/v1` | Dynamical API base. |
| `GEOCODE_URL` | `https://geocoding-api.open-meteo.com/v1/search` | Geocoding provider. |
| `UPSTREAM_TIMEOUT_SECONDS` | `60` | Upstream read timeout. |
| `UPSTREAM_MAX_RETRIES` | `2` | Retries for 429/503/5xx. |
| `TRUST_PROXY_HEADERS` | `true` | Parse `X-Forwarded-For` for the client IP. Only enable behind a trusted proxy. |
| `ENVIRONMENT` | `production` | Environment name. |

See `backend/.env.example` for a complete backend template.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health/live` | Liveness. |
| `GET` | `/health/ready` | Readiness (checks DuckDB). |
| `GET` | `/metrics` | Counters for cache, upstream, and rate limiting. |
| `GET` | `/api/runs` | Forecast runs for a product. |
| `GET` | `/api/geocode` | City search. |
| `GET` | `/api/product/{product_id}` | Data-product metadata. |
| `GET` | `/api/map-product/{product_id}` | Map-optimized virtual dataset options from STAC. |
| `POST` | `/api/point` | Batch point forecast. |
| `POST` | `/api/analysis` | Batch analysis window (max 31 days). |
| `POST` | `/mcp` | Streamable HTTP MCP tools. |
| `GET` | `/admin` | Admin console for organizations, API keys, quotas, and usage. |
| `GET`/`POST` | `/v1/sites` | Site CRUD for the API key's organization. |
| `POST` | `/v1/sites/{id}/forecast` | Decision forecast with confidence and provenance. |
| `POST` | `/v1/sites/{id}/workability` | Ranked workability windows for an operation. |
| `POST` | `/v1/sites/{id}/risk` | Weather risk flags. |
| `GET` | `/v1/usage` | Monthly usage and quota. |
| `GET` | `/prometheus/metrics` | Prometheus metrics. |

The web map lives at `/map` and renders the catalog's map-optimized Icechunk virtual datasets with the Dynamical deck.gl explorer. It is loaded on demand and uses spatial reads rather than the point API.

Variable availability differs by product. The UI disables surface variables a model does not provide and excludes unsupported models from a request instead of failing the batch.

## Decision layer and MCP

Sites belong to organizations and carry latitude, longitude, timezone, and an operation profile. The decision engine builds hourly series from GFS + GEFS, computes confidence from model spread, and evaluates operations such as `earthworks`, `concrete_pour`, `crane_lift`, `spraying`, `planting`, `harvest`, and `mining`.

MCP tools: `list_sites`, `get_site`, `forecast_site`, `workability_window`, `risk_flags`, `get_usage`, `get_operations`, `get_data_provenance`. Every tool requires an `X-API-Key` or bearer token and records usage against the organization's monthly quota.

Create an organization and key from `/admin` or with the admin API, then use:

```bash
curl https://$DOMAIN/v1/sites -H "X-API-Key: $API_KEY"
```

## Calibration, observability, and staging

- Forecast samples are persisted when decisions run; observations posted to `/v1/sites/{id}/observations` are joined into MAE/RMSE/bias/Brier/reliability reports at `/v1/sites/{id}/calibration`.
- `python backend/calibration.py <csv>` runs the standalone harness.
- `docker compose -f docker-compose.yml -f docker-compose.observability.yml up` adds Prometheus, Grafana, and Jaeger. Backend metrics are at `/prometheus/metrics`; the MCP process exposes metrics on `9091`.
- `docker compose -f docker-compose.yml -f docker-compose.staging.yml up --build` starts the staging overlay.
- `./scripts/backup.sh` and `./scripts/restore.sh <file>` handle Postgres backups. DuckDB is only a cache and can be rebuilt.
- `k6 run loadtest/k6.js` runs the smoke load test; set `BASE_URL`, `VUS`, `DURATION`, and optionally `API_KEY`.

Validation is enforced server-side: latitude/longitude bounds, product and variable allowlists, 1–25 variables, 1–10 products, `maxLeadTimeHours` 1–840, timezone-aware timestamps, and a 31-day analysis window.

## Tests and checks

```bash
# Backend
cd backend
pytest
ruff check .
black --check .

# Frontend
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
```

CI runs the backend tests/lint/format check, frontend lint/typecheck/test/build, and `docker compose build`.

## Security

- Caddy terminates TLS and adds HSTS, CSP, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and `Permissions-Policy`.
- The backend is not published to the host; only Caddy exposes ports 80/443.
- Containers run as non-root users and drop all capabilities except Caddy's `NET_BIND_SERVICE`.
- The backend validates all query inputs and uses an allowlist for data products and variables.
- The DuckDB cache is TTL-bounded and LRU-capped; expired rows are pruned on startup and periodically.
- Upstream calls pass through a process-wide outbound token bucket sized below the provider's documented limits.
- Upstream 429/503 responses are retried with jitter and `Retry-After`; repeated failures open a circuit breaker.

## Data attribution

Forecast and analysis data are provided by [Dynamical](https://dynamical.org/catalog/) from NOAA, ECMWF, and DWD. Geocoding is provided by Open-Meteo. Licenses vary by model; see [ATTRIBUTION.md](./ATTRIBUTION.md) and the catalog before redistributing data.

## License

MIT. See [LICENSE](./LICENSE).