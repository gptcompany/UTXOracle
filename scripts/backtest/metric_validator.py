"""Metric validation framework.

Provides rigorous statistical validation for on-chain metrics:
- Performance calculation (Sharpe, win rate, etc.)
- Random baseline comparison (Monte Carlo)
- Buy-and-hold baseline comparison
- Statistical significance testing (t-test, effect size)
- Cross-validation for consistency assessment
- Bootstrap confidence intervals

Pure Python implementation without external dependencies.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from scripts.backtest.baselines import (
    random_baseline,
    buyhold_baseline,
    calculate_signal_sharpe,
    calculate_win_rate,
    calculate_profit_factor,
)
from scripts.backtest.cross_validation import (
    cross_validate,
    assess_stability,
)
from scripts.backtest.metrics import (
    sortino_ratio,
    max_drawdown,
)
from scripts.backtest.statistics import (
    mean,
    t_test_vs_baseline,
    cohens_d,
    interpret_cohens_d,
    bootstrap_ci,
)


@dataclass
class MetricValidationResult:
    """Complete validation result for a single metric."""

    # Identification
    metric_name: str
    period_start: date
    period_end: date
    total_signals: int
    total_days: int

    # Performance Metrics
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float

    # Baseline Comparisons
    vs_random_sharpe: float  # Mean random baseline Sharpe
    vs_random_excess: float  # Actual Sharpe - Random mean
    vs_buyhold_sharpe: float  # Buy-and-hold Sharpe
    vs_buyhold_excess: float  # Actual Sharpe - Buy-hold

    # Statistical Significance
    t_statistic: float
    p_value: float
    confidence_interval_95: tuple[float, float]
    effect_size_cohens_d: float
    effect_size_interpretation: str
    is_significant: bool  # p < 0.05

    # Cross-Validation
    cv_sharpe_mean: float
    cv_sharpe_std: float
    cv_folds: int
    cv_is_stable: bool
    cv_interpretation: str

    # Overall Assessment
    recommendation: str  # "increase_weight", "maintain", "decrease_weight"

    def __post_init__(self):
        """Calculate derived fields."""
        # Ensure dates are date objects
        if isinstance(self.period_start, datetime):
            object.__setattr__(self, "period_start", self.period_start.date())
        if isinstance(self.period_end, datetime):
            object.__setattr__(self, "period_end", self.period_end.date())


@dataclass
class ComparativeValidationReport:
    """Comparative validation across multiple metrics."""

    generated_at: datetime
    period_start: date
    period_end: date
    metrics_tested: list[str]

    # Rankings
    ranking_by_sharpe: list[tuple[str, float]]
    ranking_by_win_rate: list[tuple[str, float]]
    ranking_by_effect_size: list[tuple[str, float]]

    # Recommendations
    increase_weight: list[str]  # Significant positive effect
    maintain_weight: list[str]  # Baseline-level performance
    decrease_weight: list[str]  # Underperforming

    # Individual Results
    results: dict[str, MetricValidationResult]


class MetricValidator:
    """Full validation pipeline for on-chain metrics."""

    def __init__(
        self,
        min_days: int = 180,
        cv_folds: int = 3,
        random_trials: int = 1000,
        significance_level: float = 0.05,
        seed: int = 42,
    ):
        """Initialize validator.

        Args:
            min_days: Minimum days of data required
            cv_folds: Number of cross-validation folds
            random_trials: Number of random baseline trials
            significance_level: p-value threshold (default 0.05)
            seed: Random seed for reproducibility
        """
        self.min_days = min_days
        self.cv_folds = cv_folds
        self.random_trials = random_trials
        self.significance_level = significance_level
        self.seed = seed

    def validate(
        self,
        metric_name: str,
        signals: list[float],
        prices: list[float],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> MetricValidationResult:
        """Run full validation pipeline.

        Args:
            metric_name: Name of the metric being validated
            signals: Signal values
            prices: Price series (must have len >= len(signals) + 1)
            start_date: Start date (for reporting)
            end_date: End date (for reporting)

        Returns:
            Complete validation result
        """
        # We need at least one more price than signals for return calculation
        n = min(len(signals), len(prices) - 1)

        if n < 1 or len(prices) < 2:
            return self._empty_result(metric_name, start_date, end_date)

        # Use current date if not provided
        if start_date is None:
            start_date = date.today()
        if end_date is None:
            end_date = date.today()

        # 1. Calculate actual performance
        actual_sharpe = calculate_signal_sharpe(signals, prices)
        actual_win_rate = calculate_win_rate(signals, prices)
        actual_profit_factor = calculate_profit_factor(signals, prices)

        # Calculate returns for Sortino and drawdown
        from scripts.backtest.baselines import _simulate_signal_returns

        returns = _simulate_signal_returns(signals, prices)
        actual_sortino = sortino_ratio(returns) if returns else 0.0

        # Approximate equity curve for drawdown
        equity = [1.0]
        for r in returns:
            equity.append(equity[-1] * (1 + r))
        actual_drawdown = max_drawdown(equity)

        # 2. Generate random baseline
        random_sharpes = random_baseline(
            signals, prices, n_trials=self.random_trials, seed=self.seed
        )
        random_mean = mean(random_sharpes) if random_sharpes else 0.0

        # 3. Calculate buy-and-hold baseline
        buyhold_sharpe = buyhold_baseline(prices)

        # 4. Statistical significance (vs random baseline)
        if random_sharpes:
            t_stat, p_val = t_test_vs_baseline(actual_sharpe, random_sharpes)
            d = cohens_d(actual_sharpe, random_sharpes)
            ci = bootstrap_ci(random_sharpes, seed=self.seed)
        else:
            t_stat, p_val = 0.0, 1.0
            d = 0.0
            ci = (0.0, 0.0)

        is_significant = p_val < self.significance_level

        # 5. Cross-validation
        cv_mean, cv_std, cv_folds = cross_validate(signals, prices, k=self.cv_folds)
        stability = assess_stability(cv_folds)

        # 6. Generate recommendation
        recommendation = self._generate_recommendation(
            actual_sharpe=actual_sharpe,
            random_mean=random_mean,
            buyhold_sharpe=buyhold_sharpe,
            is_significant=is_significant,
            effect_size=d,
            cv_is_stable=stability["is_stable"],
        )

        return MetricValidationResult(
            metric_name=metric_name,
            period_start=start_date,
            period_end=end_date,
            total_signals=n,
            total_days=n,
            sharpe_ratio=actual_sharpe,
            sortino_ratio=actual_sortino,
            max_drawdown=actual_drawdown,
            win_rate=actual_win_rate,
            profit_factor=actual_profit_factor,
            vs_random_sharpe=random_mean,
            vs_random_excess=actual_sharpe - random_mean,
            vs_buyhold_sharpe=buyhold_sharpe,
            vs_buyhold_excess=actual_sharpe - buyhold_sharpe,
            t_statistic=t_stat,
            p_value=p_val,
            confidence_interval_95=ci,
            effect_size_cohens_d=d,
            effect_size_interpretation=interpret_cohens_d(d),
            is_significant=is_significant,
            cv_sharpe_mean=cv_mean,
            cv_sharpe_std=cv_std,
            cv_folds=self.cv_folds,
            cv_is_stable=stability["is_stable"],
            cv_interpretation=stability["interpretation"],
            recommendation=recommendation,
        )

    def _generate_recommendation(
        self,
        actual_sharpe: float,
        random_mean: float,
        buyhold_sharpe: float,
        is_significant: bool,
        effect_size: float,
        cv_is_stable: bool,
    ) -> str:
        """Generate weight recommendation based on validation results.

        Recommendations:
        - increase_weight: Significant positive effect, stable
        - maintain_weight: At baseline level or inconclusive
        - decrease_weight: Underperforming or unstable

        Decision order (most restrictive first):
        1. Check for instability (blocks increase/maintain)
        2. Check for strong positive (increase)
        3. Check for clear underperformance (decrease)
        4. Default to maintain
        """
        # Unstable performance - MUST check first to block maintain/increase
        if not cv_is_stable:
            return "decrease_weight"

        # Strong positive: significant, large effect, stable
        if is_significant and effect_size > 0.5 and cv_is_stable:
            return "increase_weight"

        # Significantly negative performance (harmful signal)
        if is_significant and effect_size < -0.2:
            return "decrease_weight"

        # Clear underperformance (below random, not necessarily significant)
        if actual_sharpe < random_mean and not is_significant:
            return "decrease_weight"

        # Beats buy-and-hold with reasonable effect
        if actual_sharpe > buyhold_sharpe and effect_size > 0.2:
            return "maintain_weight"

        # Default: maintain current weight
        return "maintain_weight"

    def _empty_result(
        self,
        metric_name: str,
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> MetricValidationResult:
        """Create empty result for insufficient data."""
        return MetricValidationResult(
            metric_name=metric_name,
            period_start=start_date or date.today(),
            period_end=end_date or date.today(),
            total_signals=0,
            total_days=0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            max_drawdown=0.0,
            win_rate=0.0,
            profit_factor=0.0,
            vs_random_sharpe=0.0,
            vs_random_excess=0.0,
            vs_buyhold_sharpe=0.0,
            vs_buyhold_excess=0.0,
            t_statistic=0.0,
            p_value=1.0,
            confidence_interval_95=(0.0, 0.0),
            effect_size_cohens_d=0.0,
            effect_size_interpretation="Insufficient data",
            is_significant=False,
            cv_sharpe_mean=0.0,
            cv_sharpe_std=0.0,
            cv_folds=0,
            cv_is_stable=False,
            cv_interpretation="Insufficient data",
            recommendation="decrease_weight",
        )


def compare_metrics(
    validator: MetricValidator,
    metrics: dict[str, tuple[list[float], list[float]]],
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> ComparativeValidationReport:
    """Compare multiple metrics side-by-side.

    Args:
        validator: MetricValidator instance
        metrics: Dict of metric_name -> (signals, prices)
        start_date: Start date for reporting
        end_date: End date for reporting

    Returns:
        Comparative validation report
    """
    results = {}
    for name, (signals, prices) in metrics.items():
        results[name] = validator.validate(name, signals, prices, start_date, end_date)

    # Rankings
    by_sharpe = sorted(
        [(name, r.sharpe_ratio) for name, r in results.items()],
        key=lambda x: x[1],
        reverse=True,
    )
    by_win_rate = sorted(
        [(name, r.win_rate) for name, r in results.items()],
        key=lambda x: x[1],
        reverse=True,
    )
    by_effect = sorted(
        [(name, r.effect_size_cohens_d) for name, r in results.items()],
        key=lambda x: x[1],
        reverse=True,
    )

    # Recommendations
    increase = [n for n, r in results.items() if r.recommendation == "increase_weight"]
    maintain = [n for n, r in results.items() if r.recommendation == "maintain_weight"]
    decrease = [n for n, r in results.items() if r.recommendation == "decrease_weight"]

    return ComparativeValidationReport(
        generated_at=datetime.now(),
        period_start=start_date or date.today(),
        period_end=end_date or date.today(),
        metrics_tested=list(metrics.keys()),
        ranking_by_sharpe=by_sharpe,
        ranking_by_win_rate=by_win_rate,
        ranking_by_effect_size=by_effect,
        increase_weight=increase,
        maintain_weight=maintain,
        decrease_weight=decrease,
        results=results,
    )
