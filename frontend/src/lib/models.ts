export interface ModelDef {
  id: string;
  label: string;
  type: "Deterministic" | "Ensemble" | "Analysis";
  horizon: number;
  color: string;
  dash: number[];
  desc: string;
  members?: number;
}

export const MODELS: ModelDef[] = [
  { id: "noaa-gfs-forecast", label: "NOAA GFS", type: "Deterministic", horizon: 384, color: "#60a5fa", dash: [], desc: "Global, 0.25°, hourly updates." },
  { id: "noaa-hrrr-forecast-48-hour", label: "NOAA HRRR", type: "Deterministic", horizon: 48, color: "#34d399", dash: [], desc: "3km convection-allowing, US only." },
  { id: "ecmwf-aifs-single-forecast", label: "ECMWF AIFS", type: "Deterministic", horizon: 360, color: "#a78bfa", dash: [6, 4], desc: "ECMWF machine-learning model." },
  { id: "dwd-icon-eu-forecast-5-day", label: "DWD ICON-EU", type: "Deterministic", horizon: 120, color: "#fbbf24", dash: [2, 4], desc: "High-res Europe." },
  { id: "noaa-gefs-forecast-35-day", label: "NOAA GEFS", type: "Ensemble", horizon: 840, color: "#f472b6", dash: [], desc: "31 members, 35-day horizon.", members: 31 },
  { id: "ecmwf-ifs-ens-forecast-15-day-0-25-degree", label: "ECMWF IFS ENS", type: "Ensemble", horizon: 360, color: "#22d3ee", dash: [], desc: "50 members, 15-day horizon.", members: 50 },
  { id: "noaa-gfs-analysis", label: "NOAA GFS analysis", type: "Analysis", horizon: 0, color: "#94a3b8", dash: [1, 3], desc: "What actually happened (GFS)." },
  { id: "noaa-hrrr-analysis", label: "NOAA HRRR analysis", type: "Analysis", horizon: 0, color: "#cbd5e1", dash: [1, 3], desc: "What actually happened (HRRR)." },
];

export interface VarDef {
  id: string;
  label: string;
  unit: string;
  scale: number;
}

export const VARS: VarDef[] = [
  { id: "temperature_2m", label: "Temperature", unit: "°C", scale: 10 },
  { id: "relative_humidity_2m", label: "Humidity", unit: "%", scale: 20 },
  { id: "precipitation_surface", label: "Precipitation", unit: "mm", scale: 5 },
  { id: "total_cloud_cover_atmosphere", label: "Cloud cover", unit: "%", scale: 30 },
  { id: "downward_short_wave_radiation_flux_surface", label: "Solar radiation", unit: "W/m²", scale: 200 },
  { id: "pressure_reduced_to_mean_sea_level", label: "Pressure", unit: "hPa", scale: 10 },
  { id: "wind_u_10m", label: "Wind U", unit: "m/s", scale: 8 },
  { id: "wind_v_10m", label: "Wind V", unit: "m/s", scale: 8 },
  { id: "wind_speed", label: "Wind speed", unit: "m/s", scale: 8 },
];

export function modelLabel(id: string): string {
  return MODELS.find((m) => m.id === id)?.label || id;
}

export function modelById(id: string): ModelDef | undefined {
  return MODELS.find((m) => m.id === id);
}
