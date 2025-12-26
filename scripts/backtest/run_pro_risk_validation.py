#!/usr/bin/env python3
"""Run validation for spec-033 PRO Risk metric.

This script validates the predictive power of the PRO Risk composite indicator
against historical Bitcoin price movements, focusing on major cycle tops and bottoms:
- 2017 cycle top (December)
- 2021 cycle top (November)
- 2022 cycle bottom (November)

Each metric is validated using:
- Random baseline comparison (1000 Monte Carlo trials)
- Buy-and-hold baseline comparison
- Statistical significance testing (t-test, Cohen's d)
- Cross-validation (3-fold)

Usage:
    python -m scripts.backtest.run_pro_risk_validation

Output:
    reports/validation/
    ├── pro_risk_validation.json
    ├── pro_risk_validation.md
    └── pro_risk_cycle_analysis.md
"""

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from scripts.backtest.data_loader import (
    load_from_html,
    load_from_duckdb,
)
from scripts.backtest.metric_validator import MetricValidator
from scripts.backtest.report_generator import generate_validation_report

# PRO Risk metric

# =============================================================================
# Configuration
# =============================================================================

DEFAULT_MIN_DAYS = 180
DEFAULT_CV_FOLDS = 3
DEFAULT_RANDOM_TRIALS = 1000
DEFAULT_SEED = 42
DEFAULT_OUTPUT_DIR = "reports/validation"

# Historical cycle markers (spec-033 validation targets)
CYCLE_MARKERS = {
    "2017_top": date(2017, 12, 17),  # ~$19,500
    "2021_top": date(2021, 11, 10),  # ~$69,000
    "2022_bottom": date(2022, 11, 21),  # ~$15,500
}


# =============================================================================
# Signal Generation
# =============================================================================


def generate_pro_risk_signals(
    prices: list[float],
    dates: list[date],
    window: int = 30,
    seed: int = DEFAULT_SEED,
) -> list[float]:
    """Generate PRO Risk signals from price series.

    Since we don't have full historical data for all 6 components,
    this is a simplified version that generates signals based on
    price patterns as a proxy for the full PRO Risk calculation.

    In production, this would query DuckDB for all 6 component metrics:
    - MVRV Z-Score
    - SOPR
    - NUPL
    - Reserve Risk
    - Puell Multiple
    - HODL Waves

    Args:
        prices: Price series
        dates: Corresponding dates for each price
        window: Rolling window size for analysis
        seed: Random seed for reproducibility

    Returns:
        List of signal values (0.0 = extreme fear, 1.0 = extreme greed)
    """
    n = len(prices)
    signals = []

    for i in range(n):
        if i < window:
            # Not enough data for window - neutral signal
            signals.append(0.5)
            continue

        # Extract window of prices
        window_prices = prices[i - window : i]

        # Calculate simple metrics as proxies for PRO Risk components
        # This is a simplified backtest version - production would use real metrics

        # 1. Price momentum (proxy for MVRV-Z and NUPL)
        price_change = (window_prices[-1] - window_prices[0]) / window_prices[0]
        momentum_signal = 0.5 + (price_change * 2)  # Scale to 0-1 range

        # 2. Volatility (proxy for SOPR and Reserve Risk)
        returns = [
            (window_prices[j] - window_prices[j - 1]) / window_prices[j - 1]
            for j in range(1, len(window_prices))
        ]
        volatility = sum(abs(r) for r in returns) / len(returns)
        volatility_signal = min(1.0, volatility * 10)  # Higher vol = higher risk

        # 3. Price level relative to window (proxy for HODL waves)
        current_price = window_prices[-1]
        max_price = max(window_prices)
        min_price = min(window_prices)
        if max_price > min_price:
            price_position = (current_price - min_price) / (max_price - min_price)
        else:
            price_position = 0.5

        # Combine signals (weighted average like real PRO Risk)
        composite = (
            momentum_signal * 0.4  # Price momentum (MVRV-Z, NUPL)
            + volatility_signal * 0.3  # Volatility (SOPR, Reserve Risk)
            + price_position * 0.3  # Price position (HODL Waves, Puell)
        )

        # Clamp to [0, 1]
        composite = max(0.0, min(1.0, composite))

        signals.append(composite)

    return signals


# =============================================================================
# Data Loading
# =============================================================================


def load_historical_prices(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    min_days: int = DEFAULT_MIN_DAYS,
) -> tuple[list[float], list[date], date, date]:
    """Load historical prices from available sources.

    Attempts to load from DuckDB first, falls back to HTML files.

    Args:
        start_date: Start date (default: min_days ago)
        end_date: End date (default: today)
        min_days: Minimum days required

    Returns:
        Tuple of (prices, dates, actual_start, actual_end)
    """
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        # Protect against overflow for impossibly large min_days
        try:
            start_date = end_date - timedelta(days=min_days + 30)  # Buffer
        except OverflowError:
            # If min_days is too large, use a reasonable maximum
            start_date = date(1970, 1, 1)  # Earliest reasonable date

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
        return [], [], start_date, end_date

    # Extract prices and dates
    prices = [p.utxoracle_price for p in price_points]
    dates = [p.timestamp.date() for p in price_points]
    actual_start = dates[0]
    actual_end = dates[-1]

    return prices, dates, actual_start, actual_end


# =============================================================================
# Cycle Analysis
# =============================================================================


def analyze_cycle_markers(
    signals: list[float],
    dates: list[date],
    prices: list[float],
) -> dict:
    """Analyze PRO Risk signals at historical cycle tops/bottoms.

    Args:
        signals: PRO Risk signal values
        dates: Corresponding dates
        prices: Corresponding prices

    Returns:
        Dictionary with analysis results
    """
    results = {}

    for marker_name, marker_date in CYCLE_MARKERS.items():
        # Find closest date in our data
        closest_idx = None
        min_delta = timedelta(days=999999)

        for i, d in enumerate(dates):
            delta = abs(d - marker_date)
            if delta < min_delta:
                min_delta = delta
                closest_idx = i

        if closest_idx is not None and min_delta.days <= 7:  # Within 1 week
            signal_value = signals[closest_idx]
            actual_date = dates[closest_idx]
            actual_price = prices[closest_idx]

            # Classify expected vs actual
            if "top" in marker_name:
                expected = "extreme_greed"  # Should be high (>0.8)
                correct = signal_value >= 0.8
            else:  # bottom
                expected = "extreme_fear"  # Should be low (<0.2)
                correct = signal_value <= 0.2

            results[marker_name] = {
                "target_date": marker_date,
                "actual_date": actual_date,
                "days_offset": min_delta.days,
                "signal_value": signal_value,
                "price": actual_price,
                "expected_zone": expected,
                "correct_signal": correct,
            }

    return results


# =============================================================================
# Main Validation Runner
# =============================================================================


def run_pro_risk_validation(
    min_days: int = DEFAULT_MIN_DAYS,
    cv_folds: int = DEFAULT_CV_FOLDS,
    random_trials: int = DEFAULT_RANDOM_TRIALS,
    seed: int = DEFAULT_SEED,
    output_dir: str = DEFAULT_OUTPUT_DIR,
) -> dict:
    """Run validation for PRO Risk metric.

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
    print("UTXOracle PRO Risk Validation (spec-033)")
    print("=" * 60)

    # Load historical data
    print("\n[1/5] Loading historical price data...")
    prices, dates, start_date, end_date = load_historical_prices(min_days=min_days)

    if len(prices) < min_days:
        print(f"ERROR: Insufficient data. Got {len(prices)} days, need {min_days}.")
        print("Proceeding with available data for demonstration...")
        if len(prices) < 20:
            print("ERROR: Less than 20 days of data. Cannot continue.")
            return {}

    print(f"  Loaded {len(prices)} days: {start_date} to {end_date}")

    # Generate PRO Risk signals
    print("\n[2/5] Generating PRO Risk signals...")
    pro_risk_signals = generate_pro_risk_signals(prices, dates, seed=seed)
    print(f"  Generated {len(pro_risk_signals)} signals")

    # Create validator
    print(
        f"\n[3/5] Initializing validator (folds={cv_folds}, trials={random_trials})..."
    )
    validator = MetricValidator(
        min_days=min_days,
        cv_folds=cv_folds,
        random_trials=random_trials,
        seed=seed,
    )

    # Run validation
    print("\n[4/5] Running validation pipeline...")
    result = validator.validate(
        metric_name="pro_risk",
        signals=pro_risk_signals,
        prices=prices,
        start_date=start_date,
        end_date=end_date,
    )

    # Analyze cycle markers
    print("\n[5/5] Analyzing cycle markers...")
    cycle_analysis = analyze_cycle_markers(pro_risk_signals, dates, prices)

    # Generate report
    print("\nGenerating validation report...")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    json_path, md_path = generate_validation_report(result, output_dir)
    sig_status = "✅ SIGNIFICANT" if result.is_significant else "❌ NOT SIGNIFICANT"
    print(f"  PRO Risk: Sharpe={result.sharpe_ratio:.4f} {sig_status}")
    print(f"  → {md_path}")

    # Generate cycle analysis report
    cycle_report_path = Path(output_dir) / "pro_risk_cycle_analysis.md"
    with open(cycle_report_path, "w") as f:
        f.write("# PRO Risk Cycle Analysis\n\n")
        f.write(f"**Generated**: {datetime.now().isoformat()}\n\n")
        f.write(
            "Analysis of PRO Risk signals at historical cycle tops and bottoms.\n\n"
        )

        f.write("## Cycle Markers\n\n")
        f.write(
            "| Event | Target Date | Actual Date | Signal | Price | Expected | Correct |\n"
        )
        f.write(
            "|-------|-------------|-------------|--------|-------|----------|--------|\n"
        )

        for marker_name, data in cycle_analysis.items():
            signal_emoji = (
                "🔴"
                if data["signal_value"] < 0.2
                else "🟢"
                if data["signal_value"] > 0.8
                else "🟡"
            )
            correct_emoji = "✅" if data["correct_signal"] else "❌"

            f.write(
                f"| {marker_name} | {data['target_date']} | {data['actual_date']} | "
                f"{signal_emoji} {data['signal_value']:.2f} | ${data['price']:,.0f} | "
                f"{data['expected_zone']} | {correct_emoji} |\n"
            )

        f.write("\n## Interpretation\n\n")
        correct_count = sum(1 for d in cycle_analysis.values() if d["correct_signal"])
        total_count = len(cycle_analysis)
        accuracy = correct_count / total_count if total_count > 0 else 0.0

        f.write(f"**Accuracy**: {correct_count}/{total_count} ({accuracy:.1%})\n\n")
        f.write("The PRO Risk metric correctly identified ")
        f.write(f"{correct_count} out of {total_count} major cycle events.\n\n")

        if accuracy >= 0.67:
            f.write(
                "✅ **PASS**: PRO Risk demonstrates strong cycle detection capability.\n"
            )
        else:
            f.write("⚠️ **WARNING**: PRO Risk may need weight adjustments.\n")

    print(f"  → {cycle_report_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)

    print(f"\nSharpe Ratio: {result.sharpe_ratio:.4f}")
    print(f"Win Rate: {result.win_rate:.1%}")
    print(f"Max Drawdown: {result.max_drawdown:.1%}")
    print(f"vs Random: +{result.vs_random_excess:.4f}")
    print(f"vs Buy-Hold: +{result.vs_buyhold_excess:.4f}")
    print(f"Effect Size: {result.effect_size_interpretation}")
    print(f"Recommendation: {result.recommendation.upper()}")

    print("\nCycle Analysis:")
    for marker_name, data in cycle_analysis.items():
        status = "✅" if data["correct_signal"] else "❌"
        print(f"  {status} {marker_name}: {data['signal_value']:.2f}")

    print("\n" + "=" * 60)
    print(f"Reports saved to: {output_dir}/")
    print("=" * 60)

    return {
        "result": result,
        "cycle_analysis": cycle_analysis,
        "prices": prices,
        "dates": dates,
        "start_date": start_date,
        "end_date": end_date,
    }


# =============================================================================
# Entry Point
# =============================================================================


if __name__ == "__main__":
    run_pro_risk_validation()
