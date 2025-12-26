#!/usr/bin/env python3
"""Run validation for spec-009 metrics.

This script validates the predictive power of:
- Symbolic Dynamics (permutation entropy)
- Power Law Detector (tau estimation)
- Fractal Dimension (box-counting)

Each metric is validated using:
- Random baseline comparison (1000 Monte Carlo trials)
- Buy-and-hold baseline comparison
- Statistical significance testing (t-test, Cohen's d)
- Cross-validation (3-fold)

Usage:
    python -m scripts.backtest.run_validations

Output:
    reports/validation/
    ├── symbolic_dynamics_validation.json
    ├── symbolic_dynamics_validation.md
    ├── power_law_validation.json
    ├── power_law_validation.md
    ├── fractal_dimension_validation.json
    ├── fractal_dimension_validation.md
    └── comparative_ranking.md
"""

import random
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from scripts.backtest.data_loader import (
    load_from_html,
    load_from_duckdb,
)
from scripts.backtest.metric_validator import (
    MetricValidator,
    compare_metrics,
)
from scripts.backtest.report_generator import (
    generate_validation_report,
    generate_comparative_report,
)

# Metrics modules
from scripts.metrics.symbolic_dynamics import analyze as analyze_symbolic
from scripts.metrics.power_law import fit as fit_power_law
from scripts.metrics.fractal_dimension import analyze as analyze_fractal

# Import PRO Risk signal generator from validation module
import sys
from pathlib import Path as PathLib

# Add backtest directory to path to import pro risk validation
backtest_path = PathLib(__file__).parent
if str(backtest_path) not in sys.path:
    sys.path.insert(0, str(backtest_path))


# =============================================================================
# Configuration
# =============================================================================

DEFAULT_MIN_DAYS = 180
DEFAULT_CV_FOLDS = 3
DEFAULT_RANDOM_TRIALS = 1000
DEFAULT_SEED = 42
DEFAULT_OUTPUT_DIR = "reports/validation"


# =============================================================================
# Signal Generation (synthetic signals from metric algorithms)
# =============================================================================


def generate_symbolic_signals(
    prices: list[float],
    window: int = 30,
    order: int = 3,  # Reduced from 5 to 3 (needs 2*3!=12 points)
    seed: int = DEFAULT_SEED,
) -> list[float]:
    """Generate symbolic dynamics signals from price series.

    Uses a rolling window to compute permutation entropy and
    classify market patterns.

    Args:
        prices: Price series
        window: Rolling window size for analysis
        order: Embedding dimension for permutation entropy (default 3)
        seed: Random seed for reproducibility

    Returns:
        List of signal values (aligned with prices)
    """
    random.seed(seed)
    n = len(prices)
    signals = []

    for i in range(n):
        if i < window:
            # Not enough data for window
            signals.append(0.0)
            continue

        # Extract window of price returns
        window_prices = prices[i - window : i]
        returns = [
            (window_prices[j] - window_prices[j - 1]) / window_prices[j - 1]
            if window_prices[j - 1] > 0
            else 0.0
            for j in range(1, len(window_prices))
        ]

        if len(returns) < 12:  # Minimum for order=3
            signals.append(0.0)
            continue

        # Analyze symbolic dynamics
        result = analyze_symbolic(returns, order=order)
        signals.append(result.symbolic_vote)

    return signals


def generate_power_law_signals(
    prices: list[float],
    window: int = 30,
    seed: int = DEFAULT_SEED,
) -> list[float]:
    """Generate power law signals from price series.

    Simulates UTXO value distribution analysis by treating
    price volatility patterns as proxy for value dispersion.

    Args:
        prices: Price series
        window: Rolling window size
        seed: Random seed

    Returns:
        List of signal values
    """
    random.seed(seed)
    n = len(prices)
    signals = []

    for i in range(n):
        if i < window:
            signals.append(0.0)
            continue

        # Extract window and compute price-based pseudo-values
        window_prices = prices[i - window : i]

        # Create simulated UTXO values from price patterns
        # Use price levels and volatility to generate distribution
        simulated_values = []
        for j in range(1, len(window_prices)):
            if window_prices[j - 1] > 0:
                # Use price ratios scaled to simulate value distribution
                ratio = window_prices[j] / window_prices[j - 1]
                value = abs(ratio - 1) * window_prices[j] + 1  # Scale by price
                simulated_values.append(value)

        # Add additional synthetic samples based on window
        for j in range(len(window_prices)):
            # Simulate UTXO values proportional to price levels
            simulated_values.append(window_prices[j] / 1000 + 0.01)

        # Also add some volatility-based samples
        if len(window_prices) > 2:
            mean_price = sum(window_prices) / len(window_prices)
            for p in window_prices:
                deviation = abs(p - mean_price)
                if deviation > 0:
                    simulated_values.append(deviation + 0.01)

        # Filter out zeros and ensure we have enough samples
        simulated_values = [v for v in simulated_values if v > 0]

        if len(simulated_values) < 100:
            # Pad with random samples drawn from existing
            while len(simulated_values) < 100:
                random.seed(seed + i)
                idx = random.randint(0, len(simulated_values) - 1)
                simulated_values.append(
                    simulated_values[idx] * (0.9 + 0.2 * random.random())
                )

        # Fit power law
        result = fit_power_law(simulated_values)
        signals.append(result.power_law_vote)

    return signals


def generate_fractal_signals(
    prices: list[float],
    window: int = 50,
    seed: int = DEFAULT_SEED,
) -> list[float]:
    """Generate fractal dimension signals from price series.

    Uses price levels within window to estimate fractal dimension.

    Args:
        prices: Price series
        window: Rolling window size
        seed: Random seed

    Returns:
        List of signal values
    """
    random.seed(seed)
    n = len(prices)
    signals = []

    for i in range(n):
        if i < window:
            signals.append(0.0)
            continue

        # Extract window prices
        window_prices = prices[i - window : i]

        if len(window_prices) < 20:
            signals.append(0.0)
            continue

        # Analyze fractal dimension
        result = analyze_fractal(window_prices)
        signals.append(result.fractal_vote)

    return signals


# =============================================================================
# Data Loading
# =============================================================================


def load_historical_prices(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    min_days: int = DEFAULT_MIN_DAYS,
) -> tuple[list[float], date, date]:
    """Load historical prices from available sources.

    Attempts to load from DuckDB first, falls back to HTML files.

    Args:
        start_date: Start date (default: min_days ago)
        end_date: End date (default: today)
        min_days: Minimum days required

    Returns:
        Tuple of (prices, actual_start, actual_end)
    """
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=min_days + 30)  # Buffer

    # Try DuckDB first
    price_points = load_from_duckdb(
        datetime.combine(start_date, datetime.min.time()),
        datetime.combine(end_date, datetime.min.time()),
    )

    # Fall back to HTML if insufficient data
    if len(price_points) < min_days:
        print(f"DuckDB has only {len(price_points)} days, trying HTML...")
        html_points = load_from_html(
            datetime.combine(start_date, datetime.min.time()),
            datetime.combine(end_date, datetime.min.time()),
        )
        if len(html_points) > len(price_points):
            price_points = html_points

    if not price_points:
        return [], start_date, end_date

    # Extract prices and dates
    prices = [p.utxoracle_price for p in price_points]
    actual_start = price_points[0].timestamp.date()
    actual_end = price_points[-1].timestamp.date()

    return prices, actual_start, actual_end


# =============================================================================
# Main Validation Runner
# =============================================================================


def run_all_validations(
    min_days: int = DEFAULT_MIN_DAYS,
    cv_folds: int = DEFAULT_CV_FOLDS,
    random_trials: int = DEFAULT_RANDOM_TRIALS,
    seed: int = DEFAULT_SEED,
    output_dir: str = DEFAULT_OUTPUT_DIR,
) -> dict:
    """Run validation for all spec-009 metrics.

    Args:
        min_days: Minimum days of data required
        cv_folds: Number of cross-validation folds
        random_trials: Number of random baseline trials
        seed: Random seed for reproducibility
        output_dir: Output directory for reports

    Returns:
        Dictionary with validation results
    """
    print("=" * 60)
    print("UTXOracle Metric Validation (spec-015)")
    print("=" * 60)

    # Load historical data
    print("\n[1/6] Loading historical price data...")
    prices, start_date, end_date = load_historical_prices(min_days=min_days)

    if len(prices) < min_days:
        print(f"ERROR: Insufficient data. Got {len(prices)} days, need {min_days}.")
        print("Proceeding with available data for demonstration...")
        if len(prices) < 20:
            print("ERROR: Less than 20 days of data. Cannot continue.")
            return {}

    print(f"  Loaded {len(prices)} days: {start_date} to {end_date}")

    # Generate signals for each metric
    print("\n[2/6] Generating metric signals...")

    print("  - Symbolic Dynamics...")
    symbolic_signals = generate_symbolic_signals(prices, seed=seed)
    print(f"    Generated {len(symbolic_signals)} signals")

    print("  - Power Law...")
    power_law_signals = generate_power_law_signals(prices, seed=seed)
    print(f"    Generated {len(power_law_signals)} signals")

    print("  - Fractal Dimension...")
    fractal_signals = generate_fractal_signals(prices, seed=seed)
    print(f"    Generated {len(fractal_signals)} signals")

    print("  - PRO Risk...")
    # Need dates for PRO Risk
    dates_list = [start_date + timedelta(days=i) for i in range(len(prices))]
    pro_risk_signals = generate_pro_risk_signals(prices, dates_list, seed=seed)
    print(f"    Generated {len(pro_risk_signals)} signals")

    # Create validator
    print(
        f"\n[3/6] Initializing validator (folds={cv_folds}, trials={random_trials})..."
    )
    validator = MetricValidator(
        min_days=min_days,
        cv_folds=cv_folds,
        random_trials=random_trials,
        seed=seed,
    )

    # Prepare metrics data
    metrics_data = {
        "symbolic_dynamics": (symbolic_signals, prices),
        "power_law": (power_law_signals, prices),
        "fractal_dimension": (fractal_signals, prices),
        "pro_risk": (pro_risk_signals, prices),
    }

    # Run validation
    print("\n[4/6] Running validation pipeline...")
    report = compare_metrics(
        validator=validator,
        metrics=metrics_data,
        start_date=start_date,
        end_date=end_date,
    )

    # Generate individual reports
    print("\n[5/6] Generating validation reports...")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    for name, result in report.results.items():
        json_path, md_path = generate_validation_report(result, output_dir)
        sig_status = "✅ SIGNIFICANT" if result.is_significant else "❌ NOT SIGNIFICANT"
        print(f"  - {name}: Sharpe={result.sharpe_ratio:.4f} {sig_status}")
        print(f"    → {md_path}")

    # Generate comparative report
    print("\n[6/6] Generating comparative ranking...")
    json_path, md_path = generate_comparative_report(report, output_dir)
    print(f"  → {md_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)

    print("\nRanking by Sharpe Ratio:")
    for i, (name, sharpe) in enumerate(report.ranking_by_sharpe, 1):
        print(f"  {i}. {name}: {sharpe:.4f}")

    print("\nRecommendations:")
    if report.increase_weight:
        print(f"  📈 INCREASE WEIGHT: {', '.join(report.increase_weight)}")
    if report.maintain_weight:
        print(f"  ➡️ MAINTAIN WEIGHT: {', '.join(report.maintain_weight)}")
    if report.decrease_weight:
        print(f"  📉 DECREASE WEIGHT: {', '.join(report.decrease_weight)}")

    print("\n" + "=" * 60)
    print(f"Reports saved to: {output_dir}/")
    print("=" * 60)

    return {
        "report": report,
        "prices": prices,
        "start_date": start_date,
        "end_date": end_date,
    }


# =============================================================================
# Entry Point
# =============================================================================


if __name__ == "__main__":
    run_all_validations()
