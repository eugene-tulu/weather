import type { ApiResult, EnsembleMember, NormalizedResult } from "./types";

export function deriveWindSpeed(u?: (number | null)[], v?: (number | null)[]): (number | null)[] {
  const len = Math.max(u?.length || 0, v?.length || 0);
  const out: (number | null)[] = [];
  for (let i = 0; i < len; i++) {
    const uu = u?.[i];
    const vv = v?.[i];
    out.push(
      typeof uu === "number" && typeof vv === "number" ? Math.sqrt(uu * uu + vv * vv) : null,
    );
  }
  return out;
}

export function normalizeResult(r: ApiResult): NormalizedResult {
  if (r.status && r.status !== "ok") {
    return { ...r, _times: [], _data: {}, _ensemble: null };
  }

  const f = r.forecasts?.[0];
  const times = f?.validTimes || r.analysisTimes || [];
  const data = f?.data || r.data || {};
  const ens: EnsembleMember[] | null = f?.ensembleMembers || null;

  return { ...r, _times: times, _data: data, _ensemble: ens };
}
