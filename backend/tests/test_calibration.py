from __future__ import annotations

from calibration import brier_score, mae, reliability_bins, rmse, summarize


def test_core_metrics():
    pairs = [(1.0, 2.0), (2.0, 2.0), (3.0, 4.0)]
    assert round(mae(pairs), 4) == 0.6667
    assert round(rmse(pairs), 4) == 0.8165
    assert round(brier_score([0.9, 0.1], [1, 0]), 4) == 0.01


def test_reliability_and_summary():
    rows = [
        {"forecast": 10.0, "observed": 11.0, "probability": 0.9},
        {"forecast": 12.0, "observed": 9.0, "probability": 0.1},
    ]
    report = summarize(rows, threshold=10.0)
    assert report["count"] == 2
    assert report["brier"] == 0.01
    bins = reliability_bins([0.9, 0.1], [1, 0])
    assert len(bins) == 2
