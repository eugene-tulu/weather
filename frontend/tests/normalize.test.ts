import { describe, expect, it } from "vitest";

import { deriveWindSpeed, normalizeResult } from "@/lib/normalize";
import type { ApiResult } from "@/lib/types";

describe("normalizeResult", () => {
  it("normalizes a deterministic forecast", () => {
    const result: ApiResult = {
      dataProduct: { id: "gfs" },
      forecasts: [
        {
          initTime: "2026-01-01T00:00:00Z",
          validTimes: ["2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"],
          data: { temperature_2m: [1, null] },
        },
      ],
    };

    const normalized = normalizeResult(result);

    expect(normalized._times).toEqual(["2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"]);
    expect(normalized._data.temperature_2m).toEqual([1, null]);
    expect(normalized._ensemble).toBeNull();
  });

  it("derives deterministic wind speed from u/v components", () => {
    const result: ApiResult = {
      dataProduct: { id: "gfs" },
      forecasts: [
        {
          initTime: "2026-01-01T00:00:00Z",
          validTimes: ["2026-01-01T00:00:00Z"],
          data: { wind_u_10m: [3], wind_v_10m: [4] },
        },
      ],
    };

    expect(normalizeResult(result)._data.wind_speed).toEqual([5]);
  });

  it("normalizes an ensemble forecast", () => {
    const result: ApiResult = {
      dataProduct: { id: "gefs" },
      forecasts: [
        {
          initTime: "2026-01-01T00:00:00Z",
          validTimes: ["2026-01-01T00:00:00Z"],
          ensembleMembers: [{ member: 0, data: { temperature_2m: [1] } }],
        },
      ],
    };

    const normalized = normalizeResult(result);

    expect(normalized._ensemble).toHaveLength(1);
    expect(normalized._ensemble?.[0].data?.temperature_2m).toEqual([1]);
  });

  it("normalizes an analysis result", () => {
    const result: ApiResult = {
      dataProduct: { id: "gfs-analysis" },
      analysisTimes: ["2026-01-01T00:00:00Z"],
      data: { temperature_2m: [1] },
    };

    const normalized = normalizeResult(result);

    expect(normalized._times).toEqual(["2026-01-01T00:00:00Z"]);
    expect(normalized._data.temperature_2m).toEqual([1]);
    expect(normalized._ensemble).toBeNull();
  });

  it("keeps an error result inert", () => {
    const result: ApiResult = {
      dataProduct: { id: "gfs" },
      status: "error",
      error: "upstream failed",
    };

    const normalized = normalizeResult(result);

    expect(normalized.status).toBe("error");
    expect(normalized._times).toEqual([]);
    expect(normalized._data).toEqual({});
    expect(normalized._ensemble).toBeNull();
  });
});

describe("deriveWindSpeed", () => {
  it("combines u and v components", () => {
    expect(deriveWindSpeed([3], [4])).toEqual([5]);
    expect(deriveWindSpeed([3, null], [4, 4])).toEqual([5, null]);
  });
});
