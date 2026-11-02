export function median(values: number[]): number {
  if (values.length === 0) return 0;
  const s = [...values].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

export function percentile(values: number[], p: number): number {
  if (values.length === 0) return 0;
  const s = [...values].sort((a, b) => a - b);
  const idx = (s.length - 1) * p;
  const lo = Math.floor(idx);
  const hi = Math.ceil(idx);
  if (lo === hi) return s[lo];
  return s[lo] + (s[hi] - s[lo]) * (idx - lo);
}

export function std(values: number[]): number {
  if (values.length === 0) return 0;
  const m = values.reduce((a, b) => a + b, 0) / values.length;
  return Math.sqrt(values.reduce((a, b) => a + (b - m) ** 2, 0) / values.length);
}

export function leadHoursFrom(initTime: string, timestamp: string): number {
  return Math.round((new Date(timestamp).getTime() - new Date(initTime).getTime()) / 3.6e6);
}

export function nearestIndex(leadHours: number[], target: number): number {
  let best = 0;
  let bestDiff = Infinity;
  leadHours.forEach((h, i) => {
    const d = Math.abs(h - target);
    if (d < bestDiff) {
      bestDiff = d;
      best = i;
    }
  });
  return best;
}

export interface ConfidenceResult {
  score: number;
  label: "High" | "Medium" | "Low";
}

export function confidenceScore(avgSpread: number, avgInter: number, observedRange: number): ConfidenceResult {
  const base = Math.max(1, observedRange);
  const ns = Math.min(1, avgSpread / base);
  const ni = Math.min(1, avgInter / base);
  const score = Math.round(100 * (1 - (ns + ni) / 2));
  const label = score >= 70 ? "High" : score >= 40 ? "Medium" : "Low";
  return { score, label };
}
