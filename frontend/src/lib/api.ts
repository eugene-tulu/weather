import type { ApiResult, GeocodeResult, RunOption } from "./types";

const API = (process.env.NEXT_PUBLIC_API_BASE ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  retryAfter: string | null;

  constructor(message: string, status: number, retryAfter: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

export interface PointBody {
  latitude: number;
  longitude: number;
  products: string[];
  variables: string[];
  maxLeadTimeHours: number;
  initTime?: string;
}

export interface AnalysisBody {
  latitude: number;
  longitude: number;
  products: string[];
  variables: string[];
  startTime: string;
  endTime: string;
}

function apiUrl(path: string): string {
  return `${API}${path}`;
}

function withTimeout(
  external: AbortSignal | undefined,
  timeoutMs: number,
): { signal: AbortSignal; cleanup: () => void } {
  const controller = new AbortController();
  const timer = setTimeout(
    () => controller.abort(new DOMException("Timeout", "TimeoutError")),
    timeoutMs,
  );

  const onAbort = () => {
    clearTimeout(timer);
    controller.abort();
  };

  if (external) {
    if (external.aborted) onAbort();
    else external.addEventListener("abort", onAbort, { once: true });
  }

  return {
    signal: controller.signal,
    cleanup: () => {
      clearTimeout(timer);
      external?.removeEventListener("abort", onAbort);
    },
  };
}

async function toApiError(response: Response): Promise<ApiError> {
  let message = `Request failed (${response.status})`;
  try {
    const data = await response.json();
    if (typeof data?.detail === "string" && data.detail) {
      message = data.detail;
    } else if (typeof data?.error === "string" && data.error) {
      message = data.error;
    }
  } catch {
    try {
      const text = (await response.text()).trim();
      if (text) message = text.slice(0, 300);
    } catch {
      // Keep the status message.
    }
  }
  return new ApiError(message, response.status, response.headers.get("retry-after"));
}

export async function fetchJson<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs = 15_000,
): Promise<T> {
  const timeout = withTimeout(init.signal ?? undefined, timeoutMs);
  try {
    const response = await fetch(apiUrl(path), {
      ...init,
      signal: timeout.signal,
    });
    if (!response.ok) throw await toApiError(response);
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      if (init.signal?.aborted) throw error;
      throw new ApiError("Request timed out", 0);
    }
    throw error;
  } finally {
    timeout.cleanup();
  }
}

export function fetchForecast(
  body: PointBody,
  signal?: AbortSignal,
): Promise<{ results: ApiResult[] }> {
  return fetchJson(
    "/api/point",
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      signal,
    },
    20_000,
  );
}

export function fetchAnalysis(
  body: AnalysisBody,
  signal?: AbortSignal,
): Promise<{ results: ApiResult[] }> {
  return fetchJson(
    "/api/analysis",
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      signal,
    },
    20_000,
  );
}

export function fetchRuns(
  dataProductId: string,
  signal?: AbortSignal,
): Promise<{ runs?: RunOption[] }> {
  return fetchJson(
    `/api/runs?dataProductId=${encodeURIComponent(dataProductId)}&limit=5`,
    { signal },
    15_000,
  );
}

export function fetchGeocode(
  query: string,
  signal?: AbortSignal,
): Promise<{ results?: GeocodeResult[] }> {
  return fetchJson(`/api/geocode?q=${encodeURIComponent(query)}`, { signal }, 10_000);
}
