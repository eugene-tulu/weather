import { median, percentile, std } from "./stats";
import type { ChartRow, EnsembleMember, NormalizedResult, Stats } from "./types";

function isNum(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function mean(values: number[]): number {
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : 0;
}

function nearestIndex(arr: number[], target: number): number {
  if (!arr.length) return 0;
  let best = 0;
  let bestDist = Infinity;
  for (let i = 0; i < arr.length; i++) {
    const d = Math.abs(arr[i] - target);
    if (d < bestDist) {
      bestDist = d;
      best = i;
    }
  }
  return best;
}

export function formatTime(value: string): string {
  return value.slice(5, 16).replace("T", " ");
}

export function memberValue(
  member: EnsembleMember,
  variable: string,
  index: number,
): number | null {
  if (!member.data) return null;
  if (variable === "wind_speed") {
    const u = member.data.wind_u_10m?.[index];
    const v = member.data.wind_v_10m?.[index];
    return isNum(u) && isNum(v) ? Math.sqrt(u * u + v * v) : null;
  }
  return member.data[variable]?.[index] ?? null;
}

export function valueAtTime(
  result: NormalizedResult,
  variable: string,
  time: string,
  aggregation: "median" | "mean" = "median",
): number | null {
  const index = result._times.indexOf(time);
  if (index < 0) return null;

  if (result._ensemble) {
    const values = result._ensemble
      .map((member) => memberValue(member, variable, index))
      .filter(isNum);
    if (!values.length) return null;
    return aggregation === "mean" ? mean(values) : median(values);
  }

  return result._data[variable]?.[index] ?? null;
}

export function buildChartData(results: NormalizedResult[], variable: string): ChartRow[] {
  const timeSet = new Set<string>();
  results.forEach((result) => result._times.forEach((time) => timeSet.add(time)));
  const sorted = [...timeSet].sort();
  const ensembleModels = results.filter((result) => result._ensemble !== null);

  return sorted.map((time) => {
    const row: ChartRow = { time: formatTime(time) };

    const pooled: number[] = [];
    ensembleModels.forEach((result) => {
      const index = result._times.indexOf(time);
      if (index < 0) return;
      (result._ensemble || []).forEach((member) => {
        const value = memberValue(member, variable, index);
        if (isNum(value)) pooled.push(value);
      });
    });

    if (pooled.length) {
      row._ensMedian = median(pooled);
      row._p50Low = percentile(pooled, 0.25);
      row._p50High = percentile(pooled, 0.75);
      row._p90Low = percentile(pooled, 0.05);
      row._p90High = percentile(pooled, 0.95);
    }

    results.forEach((result) => {
      const index = result._times.indexOf(time);
      if (index < 0) return;
      const id = result.dataProduct.id;

      if (result._ensemble) {
        const values = result._ensemble
          .map((member) => memberValue(member, variable, index))
          .filter(isNum);

        if (values.length) {
          row[id] = median(values);
          row[`${id}_min`] = Math.min(...values);
          row[`${id}_max`] = Math.max(...values);
        }

        result._ensemble.forEach((member, memberIndex) => {
          const value = memberValue(member, variable, index);
          if (isNum(value)) row[`${id}_m${memberIndex}`] = value;
        });
        return;
      }

      const value = result._data[variable]?.[index];
      if (isNum(value)) row[id] = value;
    });

    return row;
  });
}

export function computeStats(
  results: NormalizedResult[],
  variable: string,
  varScale: number,
): Stats | null {
  if (!results.length) return null;

  const timeSet = new Set<string>();
  results.forEach((result) => result._times.forEach((time) => timeSet.add(time)));
  const leads = [...timeSet].sort();
  if (!leads.length) return null;

  const initTime =
    results[0]?.forecasts?.[0]?.initTime || results[0]?.analysisTimes?.[0] || leads[0];
  const leadHours = leads.map((time) =>
    Math.round((new Date(time).getTime() - new Date(initTime).getTime()) / 3.6e6),
  );
  const lastLead = leadHours[leadHours.length - 1] || 0;

  const modelValue = (result: NormalizedResult, index: number): number | null => {
    if (result._ensemble) {
      const values = result._ensemble
        .map((member) => memberValue(member, variable, index))
        .filter(isNum);
      return values.length ? median(values) : null;
    }
    return result._data[variable]?.[index] ?? null;
  };

  const modelPoints = leads.map((time) =>
    results
      .map((result) => {
        const index = result._times.indexOf(time);
        if (index < 0) return null;
        const value = modelValue(result, index);
        return isNum(value) ? value : null;
      })
      .filter(isNum),
  );

  const allMembers: (number | null)[][] = [];
  results
    .filter((result) => result._ensemble !== null)
    .forEach((result) =>
      (result._ensemble || []).forEach((member) => {
        allMembers.push(
          leads.map((time) => {
            const index = result._times.indexOf(time);
            if (index < 0) return null;
            return memberValue(member, variable, index);
          }),
        );
      }),
    );

  const ensMedian = leads.map((_, index) => {
    const values = allMembers.map((member) => member[index]).filter(isNum);
    return values.length ? median(values) : null;
  });

  const spread = leads.map((_, index) => {
    const values = allMembers.map((member) => member[index]).filter(isNum);
    return values.length > 1 ? std(values) : 0;
  });

  const multiVals = leads.map((_, index) => [
    ...modelPoints[index],
    ...(isNum(ensMedian[index]) ? [ensMedian[index]!] : []),
  ]);
  const multiMedian = multiVals.map((values) => (values.length ? median(values) : null));
  const interdev = multiVals.map((values) => (values.length > 1 ? std(values) : 0));

  const thr = varScale * 0.3;
  let agreeUntil = lastLead;
  for (let index = 0; index < leads.length; index++) {
    if ((spread[index] || 0) > thr || (interdev[index] || 0) > thr) {
      agreeUntil = leadHours[index];
      break;
    }
  }

  const maxSplit = Math.max(
    0,
    ...leads.map((_, index) => {
      const values = multiVals[index];
      if (!values.length) return 0;
      return Math.max(...values) - Math.min(...values);
    }),
  );

  const inRange = [24, 72, 168].filter((target) => target <= lastLead);
  const targets = inRange.length ? inRange : [Math.max(1, lastLead)];
  const avgSpread = targets.map((target) => spread[nearestIndex(leadHours, target)]).filter(isNum);
  const avgInter = targets.map((target) => interdev[nearestIndex(leadHours, target)]).filter(isNum);

  const perTimestampRanges = leads
    .map((_, index) => {
      const values = multiVals[index].filter(isNum);
      return values.length ? Math.max(...values) - Math.min(...values) : 0;
    })
    .filter((value) => value > 0);
  const observedRange = perTimestampRanges.length ? median(perTimestampRanges) : 1;

  const avgSpreadValue = avgSpread.length ? mean(avgSpread) : 0;
  const avgInterValue = avgInter.length ? mean(avgInter) : 0;
  const { score, label } = confidenceScore(avgSpreadValue, avgInterValue, observedRange);

  let bigH: number | null = null;
  let bigVal: number | null = null;
  let bigA: string | null = null;
  let bigB: string | null = null;

  leads.forEach((time, index) => {
    const points = results
      .map((result) => {
        const resultIndex = result._times.indexOf(time);
        if (resultIndex < 0) return null;
        const value = modelValue(result, resultIndex);
        return isNum(value) ? { id: result.dataProduct.id, value } : null;
      })
      .filter((point): point is { id: string; value: number } => point !== null);

    if (points.length < 2) return;
    points.sort((a, b) => a.value - b.value);
    const diff = points[points.length - 1].value - points[0].value;
    if (bigVal === null || diff > bigVal) {
      bigVal = diff;
      bigH = leadHours[index];
      bigA = points[0].id;
      bigB = points[points.length - 1].id;
    }
  });

  const spreadAt = (target: number) => {
    if (target > lastLead) return "—";
    const index = nearestIndex(leadHours, target);
    return (spread[index] || 0).toFixed(2);
  };

  return {
    leads,
    leadHours,
    spread,
    multiMedian,
    interdev,
    score,
    label,
    thr,
    agreeUntil,
    maxSplit,
    bigH,
    bigVal,
    bigA,
    bigB,
    spreadAt,
    runAges: results.map((result) => ({
      id: result.dataProduct.id,
      time: result.forecasts?.[0]?.initTime || result.analysisTimes?.[0] || leads[0],
    })),
    ensMedian,
  };
}

export function toCsv(
  results: NormalizedResult[],
  variable: string,
  labelFor: (id: string) => string,
): string {
  const timeSet = new Set<string>();
  results.forEach((result) => result._times.forEach((time) => timeSet.add(time)));
  const sorted = [...timeSet].sort();
  const csvCell = (value: string) => (/^[=+\-@]/.test(value) ? `'${value}` : value);
  const header = ["time", ...results.map((result) => csvCell(labelFor(result.dataProduct.id)))];
  const lines = sorted.map((time) => {
    const values = results.map((result) => {
      const value = valueAtTime(result, variable, time);
      return isNum(value) ? value.toFixed(3) : "";
    });
    return [time, ...values].join(",");
  });
  return [header.join(","), ...lines].join("\n");
}

export function formatRunAge(iso: string): string {
  const timestamp = new Date(iso).getTime();
  if (!Number.isFinite(timestamp)) return "—";
  const minutes = Math.max(0, Math.round((Date.now() - timestamp) / 60_000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

function confidenceScore(
  avgSpread: number,
  avgInter: number,
  observedRange: number,
): { score: number; label: string } {
  const base = Math.max(1, observedRange);
  const ns = Math.max(0, Math.min(1, avgSpread / base));
  const ni = Math.max(0, Math.min(1, avgInter / base));
  const penalty = ns * 65 + ni * 35;
  const score = Math.max(0, Math.min(100, Math.round(100 - penalty)));
  const label = score >= 75 ? "High" : score >= 50 ? "Moderate" : score >= 25 ? "Low" : "Very low";
  return { score, label };
}
