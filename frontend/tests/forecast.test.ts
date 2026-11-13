import { describe, expect, it } from "vitest";

import { buildChartData, computeStats, formatRunAge, toCsv, valueAtTime } from "@/lib/forecast";
import type { EnsembleMember, NormalizedResult } from "@/lib/types";

function makeResult({
  id,
  times,
  data,
  ensemble = null,
}: {
  id: string;
  times: string[];
  data: Record<string, (number | null)[]>;
  ensemble?: EnsembleMember[] | null;
}): NormalizedResult {
  return {
    dataProduct: { id },
    forecasts: [{ initTime: times[0], validTimes: times, data }],
    _times: times,
    _data: data,
    _ensemble: ensemble,
  };
}

const HOURLY = [
  "2026-01-01T00:00:00Z",
  "2026-01-01T01:00:00Z",
  "2026-01-01T02:00:00Z",
  "2026-01-01T03:00:00Z",
];

const THREE_HOURLY = ["2026-01-01T00:00:00Z", "2026-01-01T03:00:00Z"];

describe("buildChartData", () => {
  it("aligns each model to its own valid-time index", () => {
    const hourly = makeResult({
      id: "hourly",
      times: HOURLY,
      data: { temperature_2m: [1, 2, 3, 4] },
    });
    const threeHourly = makeResult({
      id: "three-hourly",
      times: THREE_HOURLY,
      data: { temperature_2m: [10, 20] },
    });

    const rows = buildChartData([hourly, threeHourly], "temperature_2m");

    expect(rows.map((row) => row.time)).toEqual([
      "01-01 00:00",
      "01-01 01:00",
      "01-01 02:00",
      "01-01 03:00",
    ]);
    expect(rows[1].hourly).toBe(2);
    expect(rows[1]["three-hourly"]).toBeUndefined();
    expect(rows[3]["three-hourly"]).toBe(20);
    expect(rows[3].hourly).toBe(4);
  });

  it("aligns pooled ensemble bands to each ensemble's own time axis", () => {
    const ensemble = makeResult({
      id: "ens",
      times: THREE_HOURLY,
      data: {},
      ensemble: [
        { member: 0, data: { temperature_2m: [0, 10] } },
        { member: 1, data: { temperature_2m: [2, 20] } },
      ],
    });
    const hourly = makeResult({
      id: "hourly",
      times: HOURLY,
      data: { temperature_2m: [1, 2, 3, 4] },
    });

    const rows = buildChartData([ensemble, hourly], "temperature_2m");

    expect(rows[0]._ensMedian).toBe(1);
    expect(rows[1]._ensMedian).toBeUndefined();
    expect(rows[3]._ensMedian).toBe(15);
    expect(rows[0].ens).toBe(1);
    expect(rows[3].ens).toBe(15);
  });

  it("uses the median for ensemble lines", () => {
    const ensemble = makeResult({
      id: "ens",
      times: THREE_HOURLY,
      data: {},
      ensemble: [
        { member: 0, data: { temperature_2m: [0, 100] } },
        { member: 1, data: { temperature_2m: [10, 0] } },
      ],
    });

    const rows = buildChartData([ensemble], "temperature_2m");

    expect(rows[0].ens).toBe(5);
    expect(rows[1].ens).toBe(50);
  });
});

describe("computeStats", () => {
  it("does not hard-code 100 confidence at short lead times", () => {
    const ensemble = makeResult({
      id: "ens",
      times: HOURLY,
      data: {},
      ensemble: [
        {
          member: 0,
          data: { temperature_2m: [0, 0, 0, 0] },
        },
        {
          member: 1,
          data: { temperature_2m: [10, 10, 10, 10] },
        },
      ],
    });

    const stats = computeStats([ensemble], "temperature_2m", 10);

    expect(stats).not.toBeNull();
    expect(stats?.score).toBeLessThan(100);
    expect(stats?.label).not.toBe("High");
  });

  it("returns a null biggest disagreement when fewer than two models exist", () => {
    const one = makeResult({
      id: "one",
      times: HOURLY,
      data: { temperature_2m: [1, 2, 3, 4] },
    });

    const stats = computeStats([one], "temperature_2m", 10);

    expect(stats?.bigA).toBeNull();
    expect(stats?.bigB).toBeNull();
    expect(stats?.bigVal).toBeNull();
  });

  it("finds the biggest inter-model disagreement", () => {
    const low = makeResult({
      id: "low",
      times: HOURLY,
      data: { temperature_2m: [1, 2, 3, 4] },
    });
    const high = makeResult({
      id: "high",
      times: HOURLY,
      data: { temperature_2m: [10, 20, 30, 40] },
    });

    const stats = computeStats([low, high], "temperature_2m", 10);

    expect(stats?.bigA).toBe("low");
    expect(stats?.bigB).toBe("high");
    expect(stats?.bigVal).toBe(36);
  });
});

describe("valueAtTime", () => {
  it("uses the ensemble median by default", () => {
    const ensemble = makeResult({
      id: "ens",
      times: THREE_HOURLY,
      data: {},
      ensemble: [
        { member: 0, data: { temperature_2m: [0, 10] } },
        { member: 1, data: { temperature_2m: [2, 20] } },
      ],
    });

    expect(valueAtTime(ensemble, "temperature_2m", THREE_HOURLY[0])).toBe(1);
    expect(valueAtTime(ensemble, "temperature_2m", THREE_HOURLY[0], "mean")).toBe(1);
  });
});

describe("toCsv", () => {
  it("writes a header and one row per timestamp", () => {
    const result = makeResult({
      id: "gfs",
      times: THREE_HOURLY,
      data: { temperature_2m: [1, 20] },
    });

    const csv = toCsv([result], "temperature_2m", (id) => id.toUpperCase());
    const lines = csv.split("\n");

    expect(lines[0]).toBe("time,GFS");
    expect(lines[1]).toBe("2026-01-01T00:00:00Z,1.000");
    expect(lines[2]).toBe("2026-01-01T03:00:00Z,20.000");
  });
});

describe("formatRunAge", () => {
  it("formats recent runs", () => {
    expect(formatRunAge(new Date().toISOString())).toBe("just now");
  });
});
