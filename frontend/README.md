# Disagreement frontend

Next.js 16 / React 19 / Recharts client for the Disagreement weather app.

## Setup

```bash
npm install
npm run dev
```

Open `http://localhost:3000`. For local development against a separately running backend, set `NEXT_PUBLIC_API_BASE=http://localhost:8000` in `frontend/.env.local` (ignored by git). In Docker, leave it empty so the browser calls the same-origin `/api` path proxied by Caddy.

## Scripts

| Command | Purpose |
| --- | --- |
| `npm run dev` | Start the development server. |
| `npm run build` | Production build (standalone output). |
| `npm start` | Start the production server. |
| `npm run lint` | ESLint. |
| `npm run typecheck` | `tsc --noEmit`. |
| `npm test` | Vitest. |
| `npm run test:watch` | Vitest watch mode. |

## Structure

- `src/app/page.tsx` — point-forecast page shell, state, URL sync, data fetching, charts, and tables.
- `src/app/map/page.tsx` — map-optimized dataset route.
- `src/components/map/` — map view and on-demand Dynamical explorer mount.
- `src/lib/types.ts` — API and view types.
- `src/lib/models.ts` — model, variable, and per-model variable availability metadata.
- `src/lib/map-products.ts` — map-optimized product catalog.
- `src/lib/normalize.ts` — API result normalization.
- `src/lib/forecast.ts` — chart alignment, statistics, CSV export.
- `src/lib/api.ts` — fetch helpers with timeout and abort handling.
- `src/lib/stats.ts` — median, percentile, standard deviation, confidence primitives.
- `tests/` — Vitest unit tests.

## Map view

`/map` lists global map-optimized Icechunk products. Selecting one fetches its STAC metadata through the backend, then loads the Dynamical deck.gl explorer on demand. The explorer bundle, S3 reads, and workers are allowed by the Caddy CSP; the backend remains the only API proxy for point data. The map is intentionally loaded only after a click so the point-forecast page stays light.

## Chart alignment

Ensemble members are aligned by each model's own `validTimes` array, not by a shared union index. This matters when hourly and 3-hourly models are shown together. Ensemble lines and the table use the median consistently.

## Accessibility

- The page has a single `<h1>`.
- Tabs expose `role="tablist"`, `role="tab"`, `aria-selected`, and arrow-key navigation.
- The modal and mobile control rail trap focus and close on Escape.
- The search field exposes combobox/listbox semantics.
- Loading, error, notice, and copy status use live regions.
- The table view is the text alternative to the chart.

## Notes

- `npm audit` is clean for production dependencies; dev/build advisories should be reviewed before release.
- The Docker build uses `output: "standalone"` and copies only the standalone server, static assets, and the non-root runtime user.
- The app does not require an account or API key; it uses the public Dynamical API and Open-Meteo geocoding. Attribution is in the footer and `ATTRIBUTION.md` at the repository root.