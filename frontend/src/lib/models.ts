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
    id: "precipitation_surface",
    label: "Precip rate",
    unit: "kg m-2 s-1",
    scale: 0.005,
  },
  { id: "wind_speed", label: "Wind speed", unit: "m/s", scale: 8 },
  {
    id: "total_cloud_cover_atmosphere",
    label: "Cloud cover",
    unit: "%",
    scale: 45,
  },
  { id: "relative_humidity_2m", label: "Rel. humidity", unit: "%", scale: 25 },
  { id: "pressure_surface", label: "Surface pressure", unit: "Pa", scale: 500 },
];

// Surface variables available in the Dynamical point API for each product.
// Source: https://stac.dynamical.org/{productId}/collection.json (cube:variables).
// wind_speed is derived from wind_u_10m + wind_v_10m.
export const MODEL_VARIABLES: Record<string, string[]> = {
  "noaa-gfs-forecast": [
    "temperature_2m",
    "precipitation_surface",
    "wind_speed",
    "total_cloud_cover_atmosphere",
    "relative_humidity_2m",
    "pressure_surface",
  ],
  "noaa-hrrr-forecast-48-hour": [
    "temperature_2m",
    "precipitation_surface",
    "wind_speed",
    "total_cloud_cover_atmosphere",
    "relative_humidity_2m",
    "pressure_surface",
  ],
  "ecmwf-aifs-single-forecast": [
    "temperature_2m",
    "precipitation_surface",
    "wind_speed",
    "total_cloud_cover_atmosphere",
    "pressure_surface",
  ],
  "dwd-icon-eu-forecast-5-day": [
    "temperature_2m",
    "precipitation_surface",
    "wind_speed",
    "total_cloud_cover_atmosphere",
    "relative_humidity_2m",
    "pressure_surface",
  ],
  "noaa-gefs-forecast-35-day": [
    "temperature_2m",
    "precipitation_surface",
    "wind_speed",
    "total_cloud_cover_atmosphere",
    "relative_humidity_2m",
    "pressure_surface",
  ],
  "ecmwf-ifs-ens-forecast-15-day-0-25-degree": [
    "temperature_2m",
    "precipitation_surface",
    "wind_speed",
    "total_cloud_cover_atmosphere",
    "pressure_surface",
  ],
  "noaa-gfs-analysis": [
    "temperature_2m",
    "precipitation_surface",
    "wind_speed",
    "total_cloud_cover_atmosphere",
    "relative_humidity_2m",
    "pressure_surface",
  ],
  "noaa-hrrr-analysis": [
    "temperature_2m",
    "precipitation_surface",
    "wind_speed",
    "total_cloud_cover_atmosphere",
    "relative_humidity_2m",
    "pressure_surface",
  ],
};

export function modelLabel(id: string) {
  return MODELS.find((m) => m.id === id)?.label || id;
}

export const COLORS: Record<string, string> = Object.fromEntries(
  MODELS.map((m) => [m.id, m.color]),
);
