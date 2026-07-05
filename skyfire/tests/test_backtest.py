import pytest

from skyfire.backtest import pct_report, spearman


def test_perfect_monotonic_correlation():
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)


def test_perfect_inverse_correlation():
    assert spearman([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)


def test_handles_ties_with_average_ranks():
    r = spearman([1, 2, 2, 3], [1, 2, 3, 4])
    assert 0.9 <= r <= 1.0


def test_requires_at_least_three_pairs():
    with pytest.raises(ValueError):
        spearman([1, 2], [1, 2])


def test_pct_report_correlation_and_hits():
    rows = [
        {"quality_pct": 80, "probability_pct": 80, "actual_score": 9},
        {"quality_pct": 60, "probability_pct": 70, "actual_score": 8},
        {"quality_pct": 30, "probability_pct": 40, "actual_score": 5},
        {"quality_pct": 10, "probability_pct": 15, "actual_score": 2},
    ]
    r = pct_report(rows)
    assert r["n"] == 4
    assert r["spearman_quality"] > 0.9
    # 命中:prob>=50 视为报烧,actual>=6 视为真烧 → TP=2 FP=0 FN=0 TN=2
    assert r["hit_rate"] == 1.0 and r["precision"] == 1.0 and r["recall"] == 1.0
