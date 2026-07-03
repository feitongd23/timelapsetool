import pytest

from skyfire.backtest import spearman


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
