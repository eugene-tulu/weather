/* eslint-disable @typescript-eslint/no-explicit-any */
export function parseUrlState() {
  const p = new URLSearchParams(window.location.search);
  return {
    lat: p.has("lat") ? Number(p.get("lat")) : 41.88,
    lon: p.has("lon") ? Number(p.get("lon")) : -87.63,
    variable: p.get("v") || "temperature_2m",
    models: p.get("models") ? p.get("models")!.split(",").filter(Boolean) : ["noaa-gfs-forecast"],
    maxLead: p.has("lead") ? Number(p.get("lead")) : 48,
    snapshot: p.get("snap") || "latest",
    theme: p.get("theme") || "dark",
  };
}

export function buildUrlState(state: Record<string, any>) {
  const params = new URLSearchParams();
  params.set("lat", String(state.lat));
  params.set("lon", String(state.lon));
  params.set("v", state.variable);
  params.set("models", state.models.join(","));
  params.set("lead", String(state.maxLead));
  params.set("snap", state.snapshot);
  params.set("theme", state.theme);
  return params.toString();
}
