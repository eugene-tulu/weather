/* eslint-disable @typescript-eslint/no-explicit-any */
export function deriveWindSpeed(u: (number | null)[], v: (number | null)[]): (number | null)[] {
  return u.map((val, i) => {
    const vv = v[i];
    return (typeof val === "number" && typeof vv === "number") ? Math.sqrt(val * val + vv * vv) : null;
  });
}

export function normalizeResult(r: any, variable: string) {
  if (r.status && r.status !== "ok") return r;
  if (r.forecasts?.[0]) {
    r._times = r.forecasts[0].validTimes || [];
    r._data = r.forecasts[0].data || {};
    r._ensemble = r.forecasts[0].ensembleMembers || null;
  } else {
    r._times = r.analysisTimes || [];
    r._data = r.data || {};
    r._ensemble = null;
  }
  if (variable === "wind_speed") {
    const u = r._data["wind_u_10m"] || [];
    const v = r._data["wind_v_10m"] || [];
    r._data["wind_speed"] = deriveWindSpeed(u, v);
  }
  if (Array.isArray(r._ensemble) && variable === "wind_speed") {
    r._ensemble.forEach((m: any) => {
      const u = m.data?.wind_u_10m || [];
      const v = m.data?.wind_v_10m || [];
      m.data = m.data || {};
      m.data.wind_speed = deriveWindSpeed(u, v);
    });
  }
  return r;
}
