# Feature Specification: Backtest Validation for spec-009 Metrics

**Feature Branch**: `015-backtest-validation`
**Created**: 2025-12-06
**Status**: Draft
**Prerequisites**: spec-009 (Advanced On-Chain Analytics), spec-012 (Backtesting Framework)
**Priority**: HIGH (2-3 days)
**Evidence Source**: Contadino Galattico - TIER R (Research Opportunity)

## Context & Motivation

### Background: Unvalidated Metrics

Three spec-009 metrics currently have **Grade C evidence** (no peer review):

| Metric | Current Status | Evidence Gap |
|--------|---------------|--------------|
| **Symbolic Dynamics** | Implemented ✅ | No published backtest |
| **Power Law Detector** | Implemented ✅ | No published backtest |
| **Fractal Dimension** | Implemented ✅ | No published backtest |

### Research Opportunity

From Contadino Galattico analysis:
> "No published research found for permutation entropy on Bitcoin transaction patterns or fractal dimension of BTC value distributions."

**Impact**: UTXOracle can generate **novel academic contributions** by publishing rigorous backtests with:
- Statistical significance tests
- Sharpe ratio comparisons
- Win rate analysis
- Confidence intervals

### Validation Requirements

Each metric needs validation against:
1. **Random baseline** - Does it beat random chance?
2. **Simple baseline** - Does it beat buy-and-hold?
3. **Cross-validation** - Is performance consistent across time periods?

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Metric Validation Report (Priority: P1)

As a Bitcoin quant researcher, I want **rigorous validation reports** for each spec-009 metric, so I can trust their predictive power and potentially publish findings.

**Why this priority**: Unvalidated metrics may be adding noise, not signal. Validation reveals true value.

**Acceptance Scenarios**:

1. **Given** Symbolic Dynamics metric on 6 months of data
   **When** backtest runs against random baseline
   **Then** report shows win rate, Sharpe, p-value

2. **Given** Power Law detector on 6 months of data
   **When** backtest runs against buy-and-hold
   **Then** report shows excess return and statistical significance

3. **Given** Fractal Dimension on 6 months of data
   **When** cross-validation runs (3-fold)
   **Then** report shows performance consistency (std dev of Sharpe < 0.5)

---

### User Story 2 - Comparative Analysis (Priority: P1)

As a Bitcoin trader, I want to know **which metrics actually improve predictions**, so I can focus on signals that matter.

**Acceptance Scenarios**:

1. **Given** all 7 spec-009 metrics
   **When** comparative backtest runs
   **Then** ranking by predictive power (Sharpe ratio)

2. **Given** metric A underperforms random baseline
   **When** report generated
   **Then** recommendation: reduce weight or remove

3. **Given** metric B significantly outperforms baseline
   **When** report generated
   **Then** recommendation: increase weight

---

### User Story 3 - Publication-Ready Output (Priority: P2)

As a researcher, I want **publication-ready validation reports**, so I can submit findings to academic venues.

**Acceptance Scenarios**:

1. **Given** backtest complete for Symbolic Dynamics
   **When** report generated
   **Then** includes: methodology, results, tables, figures (LaTeX-ready)

2. **Given** statistically significant results
   **When** report generated
   **Then** includes confidence intervals and effect sizes

---

### Edge Cases

- **What if metric performs worse than random?**
  → Report clearly, recommend weight reduction or removal.

- **What if sample size too small for significance?**
  → Report "insufficient data", minimum 180 days required.

- **What if metric shows regime-dependent performance?**
  → Include regime analysis in report.

---

## Requirements *(mandatory)*

### Functional Requirements

**Validation Framework**:
- **FR-001**: Backtest framework MUST support single-metric isolation testing
- **FR-002**: Backtest MUST compare against random baseline (shuffled signals)
- **FR-003**: Backtest MUST compare against buy-and-hold baseline
- **FR-004**: Backtest MUST perform k-fold cross-validation (default: 3-fold)

**Metrics to Validate**:
- **FR-005**: Symbolic Dynamics MUST have validation report
- **FR-006**: Power Law Detector MUST have validation report
- **FR-007**: Fractal Dimension MUST have validation report

**Statistical Rigor**:
- **FR-008**: All reports MUST include p-value (significance test)
- **FR-009**: All reports MUST include 95% confidence intervals
- **FR-010**: All reports MUST include effect size (Cohen's d)
- **FR-011**: Significance threshold: p < 0.05

**Output**:
- **FR-012**: Reports MUST be saved as JSON and Markdown
- **FR-013**: Reports MUST include visualizations (equity curves, distribution plots)
- **FR-014**: Aggregate report MUST rank metrics by predictive power

### Non-Functional Requirements

- **NFR-001**: Backtest MUST complete in <10 minutes for 6 months data
- **NFR-002**: Reports MUST be deterministic (seeded random)
- **NFR-003**: Pure Python implementation (no external ML libraries)

### Key Entities *(mandatory)*

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
    is_significant: bool  # p < 0.05

    # Cross-Validation
    cv_sharpe_mean: float
    cv_sharpe_std: float
    cv_folds: int

@dataclass
class ComparativeValidationReport:
    generated_at: datetime
    period_start: date
    period_end: date
    metrics_tested: list[str]

    # Rankings
    ranking_by_sharpe: list[tuple[str, float]]
    ranking_by_win_rate: list[tuple[str, float]]

    # Recommendations
    increase_weight: list[str]  # Outperform significantly
    maintain_weight: list[str]  # Perform at baseline
    decrease_weight: list[str]  # Underperform

    # Individual Results
    results: dict[str, MetricValidationResult]
```

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 3 metrics (Symbolic, Power Law, Fractal) have validation reports
- **SC-002**: Statistical significance clearly indicated for each metric
- **SC-003**: Cross-validation shows consistency (Sharpe std < 0.5)
- **SC-004**: Comparative ranking produced
- **SC-005**: At least one metric shows p < 0.05 (otherwise investigation needed)

### Definition of Done

- [ ] Validation framework extended for single-metric testing
- [ ] Random baseline generator implemented
- [ ] Buy-and-hold baseline calculator implemented
- [ ] K-fold cross-validation implemented
- [ ] Statistical significance tests (t-test, bootstrap) implemented
- [ ] Symbolic Dynamics validation report generated
- [ ] Power Law validation report generated
- [ ] Fractal Dimension validation report generated
- [ ] Comparative ranking report generated
- [ ] Markdown reports saved to `reports/validation/`
- [ ] JSON results saved for programmatic access
- [ ] Documentation updated with validation findings

---

## Technical Notes

### Implementation Order (KISS)

1. **Extend Backtest Framework** (~50 LOC) - Single-metric isolation
2. **Baseline Generators** (~30 LOC) - Random and buy-hold
3. **Statistical Tests** (~40 LOC) - p-value, CI, effect size
4. **Cross-Validation** (~30 LOC) - K-fold split
5. **Report Generator** (~50 LOC) - JSON + Markdown output
6. **Run Validations** (~20 LOC) - Execute for each metric

### Files to Create

- `scripts/backtest/metric_validator.py` - Validation framework
- `scripts/backtest/baselines.py` - Baseline generators
- `scripts/backtest/statistics.py` - Statistical tests
- `reports/validation/` - Output directory

### Files to Modify

- `scripts/backtest/backtester.py` - Add single-metric mode
- `scripts/daily_analysis.py` - Export individual metric signals

### Validation Methodology

```python
def validate_metric(
    metric_name: str,
    signals: list[Signal],
    prices: list[float],
    n_folds: int = 3,
    n_random_trials: int = 1000
) -> MetricValidationResult:
    """
    Rigorous metric validation with statistical tests.

    1. Calculate actual performance (Sharpe, win rate, etc.)
    2. Generate random baseline (shuffle signals, run 1000x)
    3. Calculate buy-and-hold baseline
    4. Perform t-test: actual vs random distribution
    5. Calculate effect size (Cohen's d)
    6. Run k-fold cross-validation
    7. Compute confidence intervals (bootstrap)
    """
    # Actual performance
    actual = calculate_performance(signals, prices)

    # Random baseline
    random_sharpes = []
    for _ in range(n_random_trials):
        shuffled = shuffle_signals(signals)
        random_sharpes.append(calculate_performance(shuffled, prices).sharpe)

    # Statistical test
    t_stat, p_value = ttest_1samp(random_sharpes, actual.sharpe)

    # Effect size
    cohens_d = (actual.sharpe - mean(random_sharpes)) / std(random_sharpes)

    # Cross-validation
    cv_sharpes = []
    for fold in kfold_split(signals, prices, n_folds):
        fold_perf = calculate_performance(*fold)
        cv_sharpes.append(fold_perf.sharpe)

    return MetricValidationResult(
        metric_name=metric_name,
        sharpe_ratio=actual.sharpe,
        p_value=p_value,
        effect_size_cohens_d=cohens_d,
        is_significant=p_value < 0.05,
        cv_sharpe_mean=mean(cv_sharpes),
        cv_sharpe_std=std(cv_sharpes),
        ...
    )
```

### Expected Outputs

```
reports/validation/
├── symbolic_dynamics_validation.md
├── symbolic_dynamics_validation.json
├── power_law_validation.md
├── power_law_validation.json
├── fractal_dimension_validation.md
├── fractal_dimension_validation.json
└── comparative_ranking.md
```

### Configuration

```bash
# .env additions
VALIDATION_MIN_DAYS=180
VALIDATION_CV_FOLDS=3
VALIDATION_RANDOM_TRIALS=1000
VALIDATION_SIGNIFICANCE_THRESHOLD=0.05
```

---

## Research Opportunity

### Potential Publication Titles

If validation shows significant results:

1. "Permutation Entropy of Bitcoin UTXO Distributions: A Novel Regime Detection Approach"
2. "Fractal Dimension Analysis of On-Chain Transaction Patterns"
3. "Power Law Detection in Bitcoin: Identifying Critical Market States"

### Publication Venues

- **Financial Innovation** (peer-reviewed, Bitcoin-focused)
- **arXiv** (pre-print for rapid sharing)
- **SSRN** (finance research)

---

## Out of Scope

- Hyperparameter optimization for metrics
- Machine learning ensemble methods
- Real-time validation updates
- External data source validation (derivatives, etc.)

---

## References

1. **spec-009**: Advanced On-Chain Analytics - Metrics implementation
2. **spec-012**: Backtesting Framework - Infrastructure
3. **Contadino Galattico**: Evidence-based priority analysis
4. **Omole & Enke (2024)**: "Deep Learning for Bitcoin Price Direction" - Methodology reference
