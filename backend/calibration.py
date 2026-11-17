from __future__ import annotations

import argparse
import csv
import json
import math
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def mae(pairs: Iterable[tuple[float, float]]) -> float:
    values = list(pairs)
    return (
        sum(abs(forecast - observed) for forecast, observed in values) / len(values)
        if values
        else 0.0
    )


def rmse(pairs: Iterable[tuple[float, float]]) -> float:
    values = list(pairs)
    return (
        math.sqrt(sum((forecast - observed) ** 2 for forecast, observed in values) / len(values))
        if values
        else 0.0
    )


def bias(pairs: Iterable[tuple[float, float]]) -> float:
    values = list(pairs)
    return (
        sum(forecast - observed for forecast, observed in values) / len(values) if values else 0.0
    )


def brier_score(probabilities: Iterable[float], outcomes: Iterable[int]) -> float:
    pairs = list(zip(probabilities, outcomes, strict=False))
    return (
        sum((probability - outcome) ** 2 for probability, outcome in pairs) / len(pairs)
        if pairs
        else 0.0
    )


def reliability_bins(
    probabilities: Iterable[float],
    outcomes: Iterable[int],
    bins: int = 10,
) -> list[dict[str, float | int]]:
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(bins)]
    for probability, outcome in zip(probabilities, outcomes, strict=False):
        index = min(bins - 1, max(0, int(probability * bins)))
        buckets[index].append((probability, outcome))

    result = []
    for index, bucket in enumerate(buckets):
        if not bucket:
            continue
        result.append(
            {
                "bin_start": index / bins,
                "bin_end": (index + 1) / bins,
                "count": len(bucket),
                "mean_probability": sum(p for p, _ in bucket) / len(bucket),
                "observed_frequency": sum(o for _, o in bucket) / len(bucket),
            }
        )
    return result


def summarize(rows: Iterable[dict[str, Any]], threshold: float | None = None) -> dict[str, Any]:
    values = list(rows)
    pairs = [
        (float(row["forecast"]), float(row["observed"]))
        for row in values
        if row.get("forecast") is not None and row.get("observed") is not None
    ]
    probability_rows = [
        row
        for row in values
        if row.get("probability") is not None
        and row.get("observed") is not None
        and threshold is not None
    ]
    probabilities = [float(row["probability"]) for row in probability_rows]
    outcomes = [1 if float(row["observed"]) > threshold else 0 for row in probability_rows]

    return {
        "count": len(pairs),
        "mae": round(mae(pairs), 4),
        "rmse": round(rmse(pairs), 4),
        "bias": round(bias(pairs), 4),
        "threshold": threshold,
        "brier": (round(brier_score(probabilities, outcomes), 4) if probabilities else None),
        "reliability": (reliability_bins(probabilities, outcomes) if probabilities else []),
    }


def read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calibration harness for forecast/observation CSVs."
    )
    parser.add_argument("csv", type=Path)
    parser.add_argument("--threshold", type=float, default=None)
    args = parser.parse_args()
    print(json.dumps(summarize(read_csv(args.csv), args.threshold), indent=2))


if __name__ == "__main__":
    main()
