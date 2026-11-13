import type { ModelDef, VariableDef } from "./types";

export const MODELS: ModelDef[] = [
  {
    id: "noaa-gfs-forecast",
    label: "GFS",
    desc: "Global deterministic",
    type: "Deterministic",
    horizon: 384,
    color: "#22d3ee",
  },
  {
    id: "noaa-hrrr-forecast-48-hour",
    label: "HRRR",
    desc: "US 3km · hourly",
    type: "Deterministic",
    horizon: 48,
    color: "#f59e0b",
  },
  {
    id: "ecmwf-aifs-single-forecast",
    label: "AIFS",
    desc: "ECMWF ML deterministic",
    type: "Deterministic",
    horizon: 360,
    color: "#a78bfa",
  },
  {
    id: "dwd-icon-eu-forecast-5-day",
    label: "ICON-EU",
    desc: "DWD 5-day",
    type: "Deterministic",
    horizon: 120,
    color: "#fbbf24",
  },
  {
    id: "noaa-gefs-forecast-35-day",
    label: "GEFS",
    desc: "31-member ensemble",
    type: "Ensemble",
    horizon: 840,
    color: "#e879f9",
  },
  {
    id: "ecmwf-ifs-ens-forecast-15-day-0-25-degree",
    label: "ECMWF ENS",
    desc: "51-member · 0.25°",
    type: "Ensemble",
    horizon: 360,
    color: "#34d399",
    dash: [2, 2],
  },
  {
    id: "noaa-gfs-analysis",
    label: "GFS analysis",
    desc: "What happened · 3h",
    type: "Analysis",
    horizon: 480,
    color: "#94a3b8",
    dash: [1, 2],
  },
  {
    id: "noaa-hrrr-analysis",
    label: "HRRR analysis",
    desc: "US 3km · hourly",
    type: "Analysis",
    horizon: 48,
    color: "#cbd5e1",
    dash: [1, 2],
  },
];

export const VARS: VariableDef[] = [
  { id: "temperature_2m", label: "Temperature", unit: "°C", scale: 10 },
  {
    id: "total_precipitation",
    label: "Total precip",
    unit: "kg m-2 s-1",
    scale: 8,
  },
  { id: "wind_speed", label: "Wind speed", unit: "m/s", scale: 8 },
  { id: "cloud_cover", label: "Cloud cover", unit: "%", scale: 45 },
  { id: "relative_humidity_2m", label: "Rel. humidity", unit: "%", scale: 25 },
  { id: "surface_pressure", label: "Surface pressure", unit: "hPa", scale: 18 },
  {
    id: "boundary_layer_height",
    label: "Boundary layer",
    unit: "m",
    scale: 500,
  },
];

export function modelLabel(id: string) {
  return MODELS.find((m) => m.id === id)?.label || id;
}

export const COLORS: Record<string, string> = Object.fromEntries(
  MODELS.map((m) => [m.id, m.color]),
);
