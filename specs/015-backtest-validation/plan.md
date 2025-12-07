# Implementation Plan: Backtest Validation for spec-009 Metrics

**Spec**: spec-015
**Created**: 2025-12-06
**Estimated Effort**: 2-3 days
**Priority**: HIGH

---

## Overview

This plan implements rigorous statistical validation for spec-009 metrics (Symbolic Dynamics, Power Law, Fractal Dimension) to determine their actual predictive value and generate publication-ready reports.

---

## Architecture

### Validation Framework

```
┌─────────────────────────────────────────────────────────────┐
│                    Metric Validator                          │
├─────────────────────────────────────────────────────────────┤
│  Input: Metric signals + Price data (6+ months)             │
├─────────────────────────────────────────────────────────────┤
│  1. Calculate actual performance (Sharpe, win rate, etc.)   │
│  2. Generate random baseline (1000 shuffled trials)         │
│  3. Calculate buy-and-hold baseline                         │
│  4. Statistical test: actual vs random (t-test)             │
│  5. Effect size (Cohen's d)                                 │
│  6. K-fold cross-validation (3-fold)                        │
│  7. Bootstrap confidence intervals                          │
├─────────────────────────────────────────────────────────────┤
│  Output: MetricValidationResult + Report (JSON/MD)          │
└─────────────────────────────────────────────────────────────┘
```

### Metrics to Validate

| Metric | Evidence Grade | Current Status |
|--------|---------------|----------------|
| Symbolic Dynamics | C | Implemented, no backtest |
| Power Law Detector | C | Implemented, no backtest |
| Fractal Dimension | C | Implemented, no backtest |

---

## Implementation Steps

### Step 1: Create Validation Framework
**File**: `scripts/backtest/metric_validator.py`

Core validation class:
```python
@dataclass
class MetricValidationResult:
    metric_name: str
    period_start: date
    period_end: date
    total_signals: int

    # Performance
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float

    # vs Baselines
    vs_random_excess_return: float
    vs_buyhold_excess_return: float

    # Statistical Significance
    p_value: float
    confidence_interval_95: tuple[float, float]
    effect_size_cohens_d: float
    is_significant: bool

    # Cross-Validation
    cv_sharpe_mean: float
    cv_sharpe_std: float
    cv_folds: int

class MetricValidator:
    def __init__(self, min_days: int = 180, cv_folds: int = 3):
        self.min_days = min_days
        self.cv_folds = cv_folds
        self.random_trials = 1000

    def validate(
        self,
        metric_name: str,
        signals: list[Signal],
        prices: list[float]
    ) -> MetricValidationResult:
        """Full validation pipeline."""
        pass
```

### Step 2: Implement Baseline Generators
**File**: `scripts/backtest/baselines.py`

```python
def random_baseline(
    signals: list[Signal],
    prices: list[float],
    n_trials: int = 1000,
    seed: int = 42
) -> list[float]:
    """
    Generate random baseline by shuffling signals.
    Returns list of Sharpe ratios from shuffled trials.
    """
    random.seed(seed)
    sharpes = []
    for _ in range(n_trials):
        shuffled = signals.copy()
        random.shuffle(shuffled)
        sharpe = calculate_sharpe(shuffled, prices)
        sharpes.append(sharpe)
    return sharpes

def buyhold_baseline(prices: list[float]) -> float:
    """Calculate buy-and-hold Sharpe ratio."""
    returns = [(prices[i+1] - prices[i]) / prices[i]
               for i in range(len(prices)-1)]
    return sharpe_ratio(returns)
```

### Step 3: Implement Statistical Tests
**File**: `scripts/backtest/statistics.py`

```python
def t_test_vs_baseline(
    actual: float,
    baseline_samples: list[float]
) -> tuple[float, float]:
    """
    One-sample t-test: is actual significantly different from baseline?
    Returns (t_statistic, p_value)
    """
    mean_baseline = statistics.mean(baseline_samples)
    std_baseline = statistics.stdev(baseline_samples)
    n = len(baseline_samples)

    t_stat = (actual - mean_baseline) / (std_baseline / math.sqrt(n))
    # Two-tailed p-value
    p_value = 2 * (1 - t_cdf(abs(t_stat), n-1))
    return t_stat, p_value

def cohens_d(actual: float, baseline_samples: list[float]) -> float:
    """Calculate effect size (Cohen's d)."""
    mean_baseline = statistics.mean(baseline_samples)
    std_baseline = statistics.stdev(baseline_samples)
    return (actual - mean_baseline) / std_baseline

def bootstrap_ci(
    data: list[float],
    confidence: float = 0.95,
    n_bootstrap: int = 1000
) -> tuple[float, float]:
    """Bootstrap confidence interval."""
    pass
```

### Step 4: Implement Cross-Validation
**File**: `scripts/backtest/cross_validation.py`

```python
def kfold_split(
    signals: list[Signal],
    prices: list[float],
    k: int = 3
) -> list[tuple[list[Signal], list[float]]]:
    """Split data into k folds for cross-validation."""
    n = len(signals)
    fold_size = n // k
    folds = []
    for i in range(k):
        start = i * fold_size
        end = start + fold_size if i < k-1 else n
        fold_signals = signals[start:end]
        fold_prices = prices[start:end]
        folds.append((fold_signals, fold_prices))
    return folds

def cross_validate(
    validator: MetricValidator,
    signals: list[Signal],
    prices: list[float],
    k: int = 3
) -> tuple[float, float]:
    """
    K-fold cross-validation.
    Returns (mean_sharpe, std_sharpe)
    """
    folds = kfold_split(signals, prices, k)
    sharpes = []
    for fold_signals, fold_prices in folds:
        sharpe = calculate_sharpe(fold_signals, fold_prices)
        sharpes.append(sharpe)
    return statistics.mean(sharpes), statistics.stdev(sharpes)
```

### Step 5: Implement Report Generator
**File**: `scripts/backtest/report_generator.py`

```python
def generate_validation_report(
    result: MetricValidationResult,
    output_dir: str = "reports/validation"
) -> tuple[str, str]:
    """
    Generate validation report in JSON and Markdown.
    Returns (json_path, md_path)
    """
    os.makedirs(output_dir, exist_ok=True)

    # JSON output
    json_path = f"{output_dir}/{result.metric_name}_validation.json"
    with open(json_path, "w") as f:
        json.dump(asdict(result), f, indent=2, default=str)

    # Markdown output
    md_path = f"{output_dir}/{result.metric_name}_validation.md"
    md_content = f"""
# Validation Report: {result.metric_name}

**Generated**: {datetime.now().isoformat()}
**Period**: {result.period_start} to {result.period_end}
**Signals**: {result.total_signals}

## Performance Metrics

| Metric | Value |
|--------|-------|
| Sharpe Ratio | {result.sharpe_ratio:.3f} |
| Sortino Ratio | {result.sortino_ratio:.3f} |
| Max Drawdown | {result.max_drawdown:.2%} |
| Win Rate | {result.win_rate:.2%} |

## vs Baselines

| Baseline | Excess Return |
|----------|---------------|
| Random | {result.vs_random_excess_return:+.2%} |
| Buy & Hold | {result.vs_buyhold_excess_return:+.2%} |

## Statistical Significance

| Test | Value | Interpretation |
|------|-------|----------------|
| p-value | {result.p_value:.4f} | {'Significant' if result.is_significant else 'Not significant'} |
| Cohen's d | {result.effect_size_cohens_d:.3f} | {interpret_cohens_d(result.effect_size_cohens_d)} |
| 95% CI | [{result.confidence_interval_95[0]:.3f}, {result.confidence_interval_95[1]:.3f}] | |

## Cross-Validation ({result.cv_folds}-fold)

| Metric | Value |
|--------|-------|
| Mean Sharpe | {result.cv_sharpe_mean:.3f} |
| Std Sharpe | {result.cv_sharpe_std:.3f} |
| Consistency | {'High' if result.cv_sharpe_std < 0.5 else 'Low'} |

## Recommendation

{'✅ **VALIDATED**: Metric shows statistically significant predictive power.' if result.is_significant else '⚠️ **NOT VALIDATED**: Metric does not show significant predictive power. Consider reducing weight.'}
"""
    with open(md_path, "w") as f:
        f.write(md_content)

    return json_path, md_path
```

### Step 6: Run Validations
**File**: `scripts/backtest/run_validations.py`

```python
def run_all_validations():
    """Run validation for all spec-009 metrics."""
    metrics_to_validate = [
        "symbolic_dynamics",
        "power_law",
        "fractal_dimension"
    ]

    # Load historical data
    signals_by_metric = load_historical_signals()
    prices = load_historical_prices()

    validator = MetricValidator(min_days=180, cv_folds=3)
    results = {}

    for metric_name in metrics_to_validate:
        signals = signals_by_metric[metric_name]
        result = validator.validate(metric_name, signals, prices)
        results[metric_name] = result
        generate_validation_report(result)

    # Generate comparative ranking
    generate_comparative_report(results)

    return results
```

---

## Output Structure

```
reports/validation/
├── symbolic_dynamics_validation.json
├── symbolic_dynamics_validation.md
├── power_law_validation.json
├── power_law_validation.md
├── fractal_dimension_validation.json
├── fractal_dimension_validation.md
└── comparative_ranking.md
```

---

## Testing Strategy

### Unit Tests
- Baseline generators
- Statistical tests (known values)
- Cross-validation splits

### Integration Tests
- Full validation pipeline
- Report generation

---

## Files to Create

| File | Purpose |
|------|---------|
| `scripts/backtest/metric_validator.py` | Core validation |
| `scripts/backtest/baselines.py` | Baseline generators |
| `scripts/backtest/statistics.py` | Statistical tests |
| `scripts/backtest/cross_validation.py` | K-fold CV |
| `scripts/backtest/report_generator.py` | Reports |
| `scripts/backtest/run_validations.py` | Main runner |
| `tests/test_metric_validator.py` | Tests |

---

## Success Criteria

- [ ] All 3 metrics have validation reports
- [ ] Statistical significance indicated (p < 0.05 or not)
- [ ] Cross-validation shows consistency
- [ ] Comparative ranking produced
- [ ] Reports saved to `reports/validation/`
