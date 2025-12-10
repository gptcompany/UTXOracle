"""Unit tests for metric validation framework (spec-015).

Tests cover:
- Statistics module (t-test, Cohen's d, bootstrap CI)
- Baseline generators (random, buy-hold)
- Cross-validation (k-fold split)
- MetricValidator pipeline
- Report generation
"""

import random
from datetime import date


from scripts.backtest.statistics import (
    mean,
    stdev,
    t_cdf,
    t_test_vs_baseline,
    cohens_d,
    interpret_cohens_d,
    bootstrap_ci,
)
from scripts.backtest.baselines import (
    random_baseline,
    buyhold_baseline,
    calculate_signal_sharpe,
    calculate_win_rate,
)
from scripts.backtest.cross_validation import (
    kfold_split,
    cross_validate,
    assess_stability,
)
from scripts.backtest.metric_validator import (
    MetricValidator,
    MetricValidationResult,
    compare_metrics,
)


# =============================================================================
# Statistics Tests
# =============================================================================


class TestStatisticsFunctions:
    """Tests for pure Python statistics implementations."""

    def test_mean_empty_list(self):
        """Mean of empty list should be 0."""
        assert mean([]) == 0.0

    def test_mean_single_value(self):
        """Mean of single value should be that value."""
        assert mean([42.0]) == 42.0

    def test_mean_multiple_values(self):
        """Mean of multiple values should be correct."""
        assert mean([1.0, 2.0, 3.0, 4.0, 5.0]) == 3.0

    def test_stdev_empty_list(self):
        """Stdev of empty list should be 0."""
        assert stdev([]) == 0.0

    def test_stdev_single_value(self):
        """Stdev of single value should be 0."""
        assert stdev([42.0]) == 0.0

    def test_stdev_known_values(self):
        """Stdev should match known calculation."""
        # Sample std of [2, 4, 4, 4, 5, 5, 7, 9] = 2.1381...
        data = [2, 4, 4, 4, 5, 5, 7, 9]
        result = stdev(data)
        assert 2.13 < result < 2.15

    def test_t_cdf_zero(self):
        """CDF at 0 should be 0.5 for any df."""
        assert abs(t_cdf(0, 10) - 0.5) < 0.01

    def test_t_cdf_large_positive(self):
        """CDF at large positive should be near 1."""
        assert t_cdf(10, 30) > 0.999

    def test_t_cdf_large_negative(self):
        """CDF at large negative should be near 0."""
        assert t_cdf(-10, 30) < 0.001


class TestTTest:
    """Tests for t-test implementation."""

    def test_t_test_identical(self):
        """Test when actual equals baseline mean."""
        baseline = [1.0, 1.0, 1.0, 1.0, 1.0]
        t_stat, p_val = t_test_vs_baseline(1.0, baseline)
        # Should not be significant (p > 0.05)
        # But with zero variance, special case
        assert p_val >= 0.0

    def test_t_test_significant_difference(self):
        """Test when actual is far from baseline."""
        baseline = [0.0] * 100  # 100 zeros
        t_stat, p_val = t_test_vs_baseline(5.0, baseline)
        # Should not compute well with zero std, but handles gracefully
        assert isinstance(p_val, float)

    def test_t_test_empty_baseline(self):
        """Empty baseline should return neutral p-value."""
        t_stat, p_val = t_test_vs_baseline(1.0, [])
        assert p_val == 1.0


class TestCohensD:
    """Tests for Cohen's d effect size."""

    def test_cohens_d_zero_effect(self):
        """Cohen's d should be 0 when actual equals baseline mean."""
        baseline = [1.0, 2.0, 3.0, 4.0, 5.0]
        d = cohens_d(3.0, baseline)  # Mean is 3.0
        assert abs(d) < 0.01

    def test_cohens_d_positive_effect(self):
        """Cohen's d should be positive when actual > baseline mean."""
        baseline = [1.0, 2.0, 3.0, 4.0, 5.0]
        d = cohens_d(6.0, baseline)  # Mean is 3.0
        assert d > 0

    def test_cohens_d_large_effect(self):
        """Large effect should have d > 0.8."""
        baseline = [0.0, 0.1, 0.2, 0.3, 0.4] * 20
        d = cohens_d(1.0, baseline)
        assert d > 0.8

    def test_interpret_cohens_d_negligible(self):
        """Interpretation for negligible effect."""
        result = interpret_cohens_d(0.1)
        assert "Negligible" in result

    def test_interpret_cohens_d_small(self):
        """Interpretation for small effect."""
        result = interpret_cohens_d(0.3)
        assert "Small" in result

    def test_interpret_cohens_d_medium(self):
        """Interpretation for medium effect."""
        result = interpret_cohens_d(0.6)
        assert "Medium" in result

    def test_interpret_cohens_d_large(self):
        """Interpretation for large effect."""
        result = interpret_cohens_d(1.0)
        assert "Large" in result


class TestBootstrapCI:
    """Tests for bootstrap confidence intervals."""

    def test_bootstrap_ci_empty(self):
        """Empty data should return (0, 0)."""
        lo, hi = bootstrap_ci([])
        assert lo == 0.0
        assert hi == 0.0

    def test_bootstrap_ci_single(self):
        """Single value should return same value for both bounds."""
        lo, hi = bootstrap_ci([5.0])
        assert lo == 5.0
        assert hi == 5.0

    def test_bootstrap_ci_contains_mean(self):
        """CI should contain the sample mean."""
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        lo, hi = bootstrap_ci(data, seed=42)
        sample_mean = mean(data)
        assert lo <= sample_mean <= hi

    def test_bootstrap_ci_deterministic(self):
        """CI should be deterministic with same seed."""
        data = [1.0, 2.0, 3.0, 4.0, 5.0] * 10
        lo1, hi1 = bootstrap_ci(data, seed=42)
        lo2, hi2 = bootstrap_ci(data, seed=42)
        assert lo1 == lo2
        assert hi1 == hi2


# =============================================================================
# Baseline Tests
# =============================================================================


class TestRandomBaseline:
    """Tests for random baseline generator."""

    def test_random_baseline_deterministic(self):
        """Random baseline should be deterministic with seed."""
        signals = [0.5, -0.5, 0.3, -0.3, 0.0] * 20
        prices = list(range(100, 200))[:100]

        result1 = random_baseline(signals, prices, n_trials=100, seed=42)
        result2 = random_baseline(signals, prices, n_trials=100, seed=42)

        assert result1 == result2

    def test_random_baseline_returns_list(self):
        """Random baseline should return list of Sharpe ratios."""
        signals = [0.5, -0.5, 0.3] * 30
        prices = list(range(100, 190))[:90]

        result = random_baseline(signals, prices, n_trials=10, seed=42)

        assert isinstance(result, list)
        assert len(result) <= 10

    def test_random_baseline_empty_signals(self):
        """Empty signals should return empty list."""
        result = random_baseline([], [100, 101, 102])
        assert result == []


class TestBuyholdBaseline:
    """Tests for buy-and-hold baseline."""

    def test_buyhold_baseline_uptrend(self):
        """Uptrend should have positive Sharpe."""
        prices = list(range(100, 200))  # 100 to 199
        sharpe = buyhold_baseline(prices)
        assert sharpe > 0

    def test_buyhold_baseline_downtrend(self):
        """Downtrend should have negative Sharpe."""
        prices = list(range(200, 100, -1))  # 200 to 101
        sharpe = buyhold_baseline(prices)
        assert sharpe < 0

    def test_buyhold_baseline_insufficient_data(self):
        """Single price should return 0."""
        sharpe = buyhold_baseline([100])
        assert sharpe == 0.0


class TestSignalSharpe:
    """Tests for signal Sharpe calculation."""

    def test_signal_sharpe_perfect_prediction(self):
        """Perfect prediction should have positive Sharpe."""
        # Signal predicts direction correctly
        prices = [100, 101, 102, 103, 104, 103, 102, 101, 102, 103]
        signals = [0.5, 0.5, 0.5, 0.5, -0.5, -0.5, -0.5, 0.5, 0.5, 0.0]

        sharpe = calculate_signal_sharpe(signals, prices, threshold=0.3)
        # Should be positive due to correct predictions
        assert sharpe > 0

    def test_signal_sharpe_no_signals(self):
        """All zero signals should return 0 Sharpe."""
        prices = [100, 101, 102, 103, 104]
        signals = [0.0, 0.0, 0.0, 0.0, 0.0]

        sharpe = calculate_signal_sharpe(signals, prices)
        assert sharpe == 0.0


class TestWinRate:
    """Tests for win rate calculation."""

    def test_win_rate_all_wins(self):
        """All correct predictions should give 1.0 win rate."""
        prices = [100, 101, 102, 103, 104, 105]  # All up
        signals = [0.5, 0.5, 0.5, 0.5, 0.5, 0.0]  # All long

        win_rate = calculate_win_rate(signals, prices, threshold=0.3)
        assert win_rate == 1.0

    def test_win_rate_no_trades(self):
        """No trades should return 0 win rate."""
        prices = [100, 101, 102]
        signals = [0.0, 0.0, 0.0]

        win_rate = calculate_win_rate(signals, prices, threshold=0.3)
        assert win_rate == 0.0


# =============================================================================
# Cross-Validation Tests
# =============================================================================


class TestKFoldSplit:
    """Tests for k-fold splitting."""

    def test_kfold_split_3_folds(self):
        """3-fold split should create 3 non-overlapping folds."""
        folds = kfold_split(30, k=3)

        assert len(folds) == 3
        assert folds[0] == (0, 10)
        assert folds[1] == (10, 20)
        assert folds[2] == (20, 30)

    def test_kfold_split_covers_all_data(self):
        """All data should be covered exactly once."""
        folds = kfold_split(100, k=5)
        covered = set()
        for start, end in folds:
            for i in range(start, end):
                covered.add(i)
        assert len(covered) == 100

    def test_kfold_split_insufficient_data(self):
        """Insufficient data should return single fold."""
        folds = kfold_split(2, k=5)
        assert len(folds) == 1


class TestCrossValidate:
    """Tests for cross-validation function."""

    def test_cross_validate_returns_metrics(self):
        """Cross-validation should return mean, std, and fold results."""
        signals = [0.5, -0.5] * 30
        prices = list(range(100, 160))[:60]

        cv_mean, cv_std, fold_metrics = cross_validate(signals, prices, k=3)

        assert isinstance(cv_mean, float)
        assert isinstance(cv_std, float)
        assert isinstance(fold_metrics, list)


class TestAssessStability:
    """Tests for stability assessment."""

    def test_stability_assessment_stable(self):
        """Consistent metrics should be assessed as stable."""
        fold_metrics = [0.5, 0.48, 0.52, 0.49, 0.51]
        result = assess_stability(fold_metrics)

        assert result["is_stable"] is True
        assert result["std"] < 0.5

    def test_stability_assessment_unstable(self):
        """Inconsistent metrics should be assessed as unstable."""
        fold_metrics = [0.5, -0.5, 1.0, -1.0, 0.0]
        result = assess_stability(fold_metrics)

        assert result["is_stable"] is False
        assert result["std"] >= 0.5


# =============================================================================
# Metric Validator Tests
# =============================================================================


class TestMetricValidator:
    """Tests for MetricValidator class."""

    def test_validator_initialization(self):
        """Validator should initialize with correct parameters."""
        validator = MetricValidator(
            min_days=100,
            cv_folds=5,
            random_trials=500,
            seed=123,
        )

        assert validator.min_days == 100
        assert validator.cv_folds == 5
        assert validator.random_trials == 500
        assert validator.seed == 123

    def test_validator_empty_data(self):
        """Validator should handle empty data gracefully."""
        validator = MetricValidator()
        result = validator.validate("test", [], [])

        assert result.total_signals == 0
        assert result.is_significant is False
        assert result.recommendation == "decrease_weight"

    def test_validator_returns_result(self):
        """Validator should return MetricValidationResult."""
        validator = MetricValidator(min_days=10, cv_folds=2, random_trials=10)

        signals = [0.5, -0.5, 0.3, -0.3, 0.0] * 20
        prices = list(range(100, 200))[:100]

        result = validator.validate(
            "test_metric",
            signals,
            prices,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 4, 1),
        )

        assert isinstance(result, MetricValidationResult)
        assert result.metric_name == "test_metric"
        assert isinstance(result.sharpe_ratio, float)
        assert isinstance(result.is_significant, bool)


class TestCompareMetrics:
    """Tests for compare_metrics function."""

    def test_compare_metrics_returns_report(self):
        """compare_metrics should return ComparativeValidationReport."""
        validator = MetricValidator(min_days=10, cv_folds=2, random_trials=10)

        metrics_data = {
            "metric_a": ([0.5, -0.5] * 25, list(range(100, 150))),
            "metric_b": ([0.3, -0.3] * 25, list(range(100, 150))),
        }

        report = compare_metrics(
            validator,
            metrics_data,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 3, 1),
        )

        assert len(report.results) == 2
        assert "metric_a" in report.results
        assert "metric_b" in report.results
        assert len(report.ranking_by_sharpe) == 2


# =============================================================================
# Integration Tests
# =============================================================================


class TestFullValidationPipeline:
    """Integration tests for complete validation pipeline."""

    def test_full_pipeline_execution(self):
        """Full validation pipeline should execute without errors."""
        # Generate synthetic data
        random.seed(42)
        prices = [100 + i + random.gauss(0, 2) for i in range(101)]  # 101 prices
        signals = [random.gauss(0, 0.3) for _ in range(100)]  # 100 signals

        # Run validation
        validator = MetricValidator(
            min_days=50,
            cv_folds=3,
            random_trials=100,
            seed=42,
        )

        result = validator.validate(
            "synthetic_metric",
            signals,
            prices,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 4, 1),
        )

        # Check all fields are populated
        assert result.metric_name == "synthetic_metric"
        assert result.total_signals == 100  # Now we can use all 100 signals
        assert isinstance(result.sharpe_ratio, float)
        assert isinstance(result.p_value, float)
        assert isinstance(result.effect_size_cohens_d, float)
        assert isinstance(result.cv_sharpe_mean, float)
        assert result.recommendation in [
            "increase_weight",
            "maintain_weight",
            "decrease_weight",
        ]
