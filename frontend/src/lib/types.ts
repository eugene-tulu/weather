export type ModelType = "Deterministic" | "Ensemble" | "Analysis";

export interface ModelDef {
  id: string;
  label: string;
  desc: string;
  type: ModelType;
  horizon: number;
  color: string;
  dash?: number[];
}

export interface VariableDef {
  id: string;
  label: string;
  unit: string;
  scale: number;
}

export interface GeocodeResult {
  id?: number | string;
  name: string;
  latitude: number;
  longitude: number;
  country?: string;
  admin1?: string;
}

export interface EnsembleMember {
  member?: number | string;
  data?: Record<string, (number | null)[]>;
}

export interface ForecastEntry {
  initTime: string;
  validTimes: string[];
  leadTimeHours?: number[];
  data?: Record<string, (number | null)[]>;
  ensembleMembers?: EnsembleMember[];
}

export interface ApiResult {
  dataProduct: { id: string; version?: string };
  forecasts?: ForecastEntry[];
  analysisTimes?: string[];
  data?: Record<string, (number | null)[]>;
  status?: string;
  error?: string;
  code?: number;
  retryAfter?: number | string | null;
  [key: string]: unknown;
}

export interface NormalizedResult extends ApiResult {
  _times: string[];
  _data: Record<string, (number | null)[]>;
  _ensemble: EnsembleMember[] | null;
}

export interface ChartRow {
  time: string;
  [key: string]: number | string | null | undefined;
}

export interface Stats {
  leads: string[];
  leadHours: number[];
  spread: number[];
  multiMedian: (number | null)[];
  interdev: number[];
  score: number;
  label: string;
  thr: number;
  agreeUntil: number;
  maxSplit: number;
  bigH: number | null;
  bigVal: number | null;
  bigA: string | null;
  bigB: string | null;
  spreadAt: (target: number) => string;
  runAges: { id: string; time: string }[];
  ensMedian: (number | null)[];
}

export interface RunOption {
  initTime: string;
}

export interface MapVariable {
  path: string;
  name: string;
  long_name: string;
  units: string;
  dims: string[];
}

export interface MapProductOptions {
  id: string;
  href: string;
  variables: MapVariable[];
  defaultVariable: string;
  initialView: { bounds: number[] };
  proj4: unknown;
  virtual: boolean;
}

export interface MapProduct {
  id: string;
  label: string;
  description: string;
  domain: string;
  resolution: string;
  cadence: string;
}
