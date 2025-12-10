"""Cross-validation for metric validation.

Implements k-fold cross-validation to ensure metric
performance is consistent across different time periods.

Time-series aware: Uses contiguous blocks to preserve
temporal structure of financial data.
"""

from scripts.backtest.statistics import mean, stdev


def kfold_split(
    data_length: int,
    k: int = 3,
) -> list[tuple[int, int]]:
    """Split data indices into k folds.

    For time series, we use contiguous blocks rather than
    random sampling to preserve temporal structure.

    Args:
        data_length: Total number of data points
        k: Number of folds

    Returns:
        List of (start_idx, end_idx) tuples for each fold
    """
    if data_length < k:
        return [(0, data_length)]

    fold_size = data_length // k
    folds = []

    for i in range(k):
        start = i * fold_size
        # Last fold gets any remaining data
        end = (i + 1) * fold_size if i < k - 1 else data_length
        folds.append((start, end))

    return folds


def cross_validate(
    signals: list[float],
    prices: list[float],
    k: int = 3,
    metric_fn=None,
) -> tuple[float, float, list[float]]:
    """K-fold cross-validation for signal performance.

    Tests whether signal performance is consistent across
    different time periods.

    Args:
        signals: Signal values
        prices: Corresponding prices (must have len >= len(signals) + 1)
        k: Number of folds (default: 3)
        metric_fn: Function to calculate metric (default: sharpe_ratio)

    Returns:
        Tuple of (mean_metric, std_metric, all_fold_metrics)
    """
    if metric_fn is None:
        from scripts.backtest.baselines import calculate_signal_sharpe

        metric_fn = calculate_signal_sharpe

    # We need at least one more price than signals for return calculation
    n = min(len(signals), len(prices) - 1)
    if n < k * 2:  # Need at least 2 signals per fold
        return 0.0, 0.0, []

    folds = kfold_split(n, k)
    fold_metrics = []

    for start, end in folds:
        fold_signals = signals[start:end]
        # Need one extra price point for return calculation
        fold_prices = prices[start : end + 1]

        if len(fold_signals) >= 2 and len(fold_prices) >= 3:
            metric = metric_fn(fold_signals, fold_prices)
            fold_metrics.append(metric)

    if not fold_metrics:
        return 0.0, 0.0, []

    return mean(fold_metrics), stdev(fold_metrics), fold_metrics


def walk_forward_validate(
    signals: list[float],
    prices: list[float],
    train_ratio: float = 0.7,
    n_splits: int = 3,
    metric_fn=None,
) -> tuple[float, float, list[float]]:
    """Walk-forward validation (expanding window).

    More realistic for trading: train on past, test on future.

    Args:
        signals: Signal values
        prices: Corresponding prices (must have len >= len(signals) + 1)
        train_ratio: Fraction of each window used for training
        n_splits: Number of walk-forward windows
        metric_fn: Function to calculate metric

    Returns:
        Tuple of (mean_metric, std_metric, all_split_metrics)
    """
    if metric_fn is None:
        from scripts.backtest.baselines import calculate_signal_sharpe

        metric_fn = calculate_signal_sharpe

    # We need at least one more price than signals for return calculation
    n = min(len(signals), len(prices) - 1)
    if n < 20:  # Need reasonable data
        return 0.0, 0.0, []

    split_size = n // n_splits
    split_metrics = []

    for i in range(n_splits):
        # Training data: everything up to this split
        train_end = (i + 1) * split_size
        test_start = train_end
        test_end = min(test_start + split_size, n)

        if test_start >= n or test_end <= test_start:
            continue

        # We only evaluate on test data
        # (Training would be used for parameter optimization)
        test_signals = signals[test_start:test_end]
        # Need one extra price point for return calculation
        test_prices = prices[test_start : test_end + 1]

        if len(test_signals) >= 2 and len(test_prices) >= 3:
            metric = metric_fn(test_signals, test_prices)
            split_metrics.append(metric)

    if not split_metrics:
        return 0.0, 0.0, []

    return mean(split_metrics), stdev(split_metrics), split_metrics


def assess_stability(
    fold_metrics: list[float],
    significance_threshold: float = 0.5,
) -> dict:
    """Assess stability of cross-validation results.

    Args:
        fold_metrics: Metrics from each fold
        significance_threshold: Max std for "stable" classification

    Returns:
        Dictionary with stability assessment
    """
    if not fold_metrics:
        return {
            "is_stable": False,
            "mean": 0.0,
            "std": 0.0,
            "cv": float("inf"),
            "min_fold": 0.0,
            "max_fold": 0.0,
            "interpretation": "Insufficient data",
        }

    m = mean(fold_metrics)
    s = stdev(fold_metrics)
    cv = s / abs(m) if m != 0 else float("inf")

    is_stable = s < significance_threshold

    # Interpretation
    if not fold_metrics:
        interpretation = "No data"
    elif len(fold_metrics) == 1:
        interpretation = "Single fold - stability unknown"
    elif is_stable:
        if m > 0:
            interpretation = f"Stable positive performance (CV={cv:.2f})"
        elif m < 0:
            interpretation = f"Stable negative performance (CV={cv:.2f})"
        else:
            interpretation = "Stable zero performance"
    else:
        interpretation = f"Unstable performance (CV={cv:.2f})"

    return {
        "is_stable": is_stable,
        "mean": m,
        "std": s,
        "cv": cv,
        "min_fold": min(fold_metrics),
        "max_fold": max(fold_metrics),
        "interpretation": interpretation,
    }


def time_series_split(
    data_length: int,
    n_splits: int = 5,
    test_size: int | None = None,
) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """Time series cross-validation split (expanding window).

    Unlike k-fold, this respects temporal ordering:
    train on past, validate on future.

    Args:
        data_length: Total number of data points
        n_splits: Number of splits
        test_size: Size of each test set (default: 1/n_splits of data)

    Returns:
        List of ((train_start, train_end), (test_start, test_end))
    """
    if test_size is None:
        test_size = data_length // (n_splits + 1)

    if test_size < 1:
        test_size = 1

    splits = []
    min_train_size = test_size  # At least as much training as test

    for i in range(n_splits):
        test_end = data_length - i * test_size
        test_start = test_end - test_size

        if test_start < min_train_size:
            break

        train_start = 0
        train_end = test_start

        splits.append(((train_start, train_end), (test_start, test_end)))

    # Reverse to go from earliest to latest
    return list(reversed(splits))
