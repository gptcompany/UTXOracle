"""Report generator for metric validation.

Generates validation reports in JSON and Markdown formats:
- Individual metric validation reports
- Comparative ranking reports
- Publication-ready formatting
"""

import json
import os
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.backtest.metric_validator import (
        MetricValidationResult,
        ComparativeValidationReport,
    )


def _serialize_for_json(obj):
    """Custom JSON serializer for dataclasses with dates and special floats.

    Handles:
    - date/datetime objects → ISO format strings
    - tuples → lists
    - inf/-inf/nan → string representations (JSON spec compliant)
    """
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, tuple):
        return list(obj)
    if isinstance(obj, float):
        if math.isinf(obj):
            return "inf" if obj > 0 else "-inf"
        if math.isnan(obj):
            return "nan"
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def generate_validation_report(
    result: "MetricValidationResult",
    output_dir: str = "reports/validation",
) -> tuple[str, str]:
    """Generate validation report in JSON and Markdown.

    Args:
        result: MetricValidationResult to report
        output_dir: Output directory for reports

    Returns:
        Tuple of (json_path, md_path)
    """
    os.makedirs(output_dir, exist_ok=True)

    # Sanitize metric name for filename
    safe_name = result.metric_name.lower().replace(" ", "_").replace("/", "_")

    # JSON output
    json_path = Path(output_dir) / f"{safe_name}_validation.json"
    with open(json_path, "w") as f:
        json.dump(asdict(result), f, indent=2, default=_serialize_for_json)

    # Markdown output
    md_path = Path(output_dir) / f"{safe_name}_validation.md"
    md_content = _format_validation_markdown(result)
    with open(md_path, "w") as f:
        f.write(md_content)

    return str(json_path), str(md_path)


def _format_validation_markdown(result: "MetricValidationResult") -> str:
    """Format validation result as Markdown."""
    sig_emoji = "✅" if result.is_significant else "⚠️"
    stable_emoji = "✅" if result.cv_is_stable else "⚠️"

    # Recommendation formatting
    rec_map = {
        "increase_weight": "📈 **INCREASE WEIGHT**: Metric shows significant predictive power",
        "maintain_weight": "➡️ **MAINTAIN WEIGHT**: Metric performs at baseline level",
        "decrease_weight": "📉 **DECREASE WEIGHT**: Metric underperforms or is unstable",
    }
    rec_text = rec_map.get(result.recommendation, "Unknown recommendation")

    return f"""# Validation Report: {result.metric_name}

**Generated**: {datetime.now().isoformat()}
**Period**: {result.period_start} to {result.period_end}
**Data Points**: {result.total_signals} signals over {result.total_days} days

---

## Performance Metrics

| Metric | Value | Interpretation |
|--------|-------|----------------|
| Sharpe Ratio | {result.sharpe_ratio:.4f} | {"Excellent" if result.sharpe_ratio > 1.5 else "Good" if result.sharpe_ratio > 0.5 else "Poor"} |
| Sortino Ratio | {result.sortino_ratio:.4f} | Downside-adjusted returns |
| Max Drawdown | {result.max_drawdown:.2%} | Peak-to-trough decline |
| Win Rate | {result.win_rate:.2%} | Profitable trades |
| Profit Factor | {result.profit_factor:.2f} | Gross profit / Gross loss |

---

## Baseline Comparisons

| Baseline | Sharpe | Excess Return |
|----------|--------|---------------|
| Random Baseline | {result.vs_random_sharpe:.4f} | {result.vs_random_excess:+.4f} |
| Buy & Hold | {result.vs_buyhold_sharpe:.4f} | {result.vs_buyhold_excess:+.4f} |

### Interpretation

- **vs Random**: Metric {"outperforms" if result.vs_random_excess > 0 else "underperforms"} random signals by {abs(result.vs_random_excess):.4f} Sharpe
- **vs Buy & Hold**: Metric {"outperforms" if result.vs_buyhold_excess > 0 else "underperforms"} passive strategy by {abs(result.vs_buyhold_excess):.4f} Sharpe

---

## Statistical Significance

| Test | Value | Interpretation |
|------|-------|----------------|
| t-statistic | {result.t_statistic:.4f} | Distance from null hypothesis |
| p-value | {result.p_value:.6f} | {sig_emoji} {"Significant" if result.is_significant else "Not significant"} (α=0.05) |
| Cohen's d | {result.effect_size_cohens_d:.4f} | {result.effect_size_interpretation} |
| 95% CI | [{result.confidence_interval_95[0]:.4f}, {result.confidence_interval_95[1]:.4f}] | Baseline mean range |

### Statistical Conclusion

{sig_emoji} **{"SIGNIFICANT" if result.is_significant else "NOT SIGNIFICANT"}**:
{"The metric's performance is statistically distinguishable from random at p < 0.05. This means there is less than a 5% probability that the observed results are due to chance." if result.is_significant else f"The metric's performance is NOT statistically distinguishable from random (p = {result.p_value:.4f}). This means the observed results could reasonably occur by chance."}

---

## Cross-Validation ({result.cv_folds}-fold)

| Metric | Value | Interpretation |
|--------|-------|----------------|
| Mean Sharpe | {result.cv_sharpe_mean:.4f} | Average across folds |
| Std Sharpe | {result.cv_sharpe_std:.4f} | Consistency measure |
| Stability | {stable_emoji} {result.cv_interpretation} | |

### Consistency Assessment

{stable_emoji} **{"STABLE" if result.cv_is_stable else "UNSTABLE"}**:
{"Performance is consistent across different time periods (std < 0.5). This increases confidence in the metric's reliability." if result.cv_is_stable else f"Performance varies significantly across time periods (std = {result.cv_sharpe_std:.4f}). The metric may be regime-dependent or overfit to specific conditions."}

---

## Recommendation

{rec_text}

### Decision Matrix

| Criterion | Status | Weight |
|-----------|--------|--------|
| Statistical Significance | {sig_emoji} {"Pass" if result.is_significant else "Fail"} | 40% |
| Effect Size > 0.2 | {"✅ Pass" if abs(result.effect_size_cohens_d) > 0.2 else "❌ Fail"} | 30% |
| Cross-Validation Stable | {stable_emoji} {"Pass" if result.cv_is_stable else "Fail"} | 30% |

---

## Summary

**{result.metric_name}** validation result:

- **Performance**: Sharpe = {result.sharpe_ratio:.4f}, Win Rate = {result.win_rate:.2%}
- **Significance**: p = {result.p_value:.6f} ({sig_emoji})
- **Effect Size**: Cohen's d = {result.effect_size_cohens_d:.4f} ({result.effect_size_interpretation})
- **Stability**: {result.cv_interpretation}
- **Recommendation**: {result.recommendation.replace("_", " ").title()}

---

*Report generated by UTXOracle Metric Validator*
*Statistical methodology: Monte Carlo baseline (1000 trials), t-test, Bootstrap CI*
"""


def generate_comparative_report(
    report: "ComparativeValidationReport",
    output_dir: str = "reports/validation",
) -> tuple[str, str]:
    """Generate comparative ranking report.

    Args:
        report: ComparativeValidationReport
        output_dir: Output directory

    Returns:
        Tuple of (json_path, md_path)
    """
    os.makedirs(output_dir, exist_ok=True)

    # JSON output
    json_path = Path(output_dir) / "comparative_ranking.json"
    with open(json_path, "w") as f:
        # Convert to serializable format
        data = {
            "generated_at": report.generated_at.isoformat(),
            "period_start": report.period_start.isoformat(),
            "period_end": report.period_end.isoformat(),
            "metrics_tested": report.metrics_tested,
            "ranking_by_sharpe": report.ranking_by_sharpe,
            "ranking_by_win_rate": report.ranking_by_win_rate,
            "ranking_by_effect_size": report.ranking_by_effect_size,
            "increase_weight": report.increase_weight,
            "maintain_weight": report.maintain_weight,
            "decrease_weight": report.decrease_weight,
            "results": {
                name: asdict(result) for name, result in report.results.items()
            },
        }
        json.dump(data, f, indent=2, default=_serialize_for_json)

    # Markdown output
    md_path = Path(output_dir) / "comparative_ranking.md"
    md_content = _format_comparative_markdown(report)
    with open(md_path, "w") as f:
        f.write(md_content)

    return str(json_path), str(md_path)


def _format_comparative_markdown(report: "ComparativeValidationReport") -> str:
    """Format comparative report as Markdown."""

    # Ranking tables
    sharpe_table = "\n".join(
        f"| {i + 1} | {name} | {sharpe:.4f} |"
        for i, (name, sharpe) in enumerate(report.ranking_by_sharpe)
    )

    winrate_table = "\n".join(
        f"| {i + 1} | {name} | {rate:.2%} |"
        for i, (name, rate) in enumerate(report.ranking_by_win_rate)
    )

    effect_table = "\n".join(
        f"| {i + 1} | {name} | {d:.4f} |"
        for i, (name, d) in enumerate(report.ranking_by_effect_size)
    )

    # Summary table
    summary_rows = []
    for name, result in report.results.items():
        sig = "✅" if result.is_significant else "❌"
        stable = "✅" if result.cv_is_stable else "❌"
        rec_emoji = {
            "increase_weight": "📈",
            "maintain_weight": "➡️",
            "decrease_weight": "📉",
        }.get(result.recommendation, "?")

        summary_rows.append(
            f"| {name} | {result.sharpe_ratio:.4f} | {result.win_rate:.2%} | "
            f"{result.effect_size_cohens_d:.2f} | {sig} | {stable} | {rec_emoji} |"
        )
    summary_table = "\n".join(summary_rows)

    # Recommendation lists
    increase_list = (
        ", ".join(report.increase_weight) if report.increase_weight else "None"
    )
    maintain_list = (
        ", ".join(report.maintain_weight) if report.maintain_weight else "None"
    )
    decrease_list = (
        ", ".join(report.decrease_weight) if report.decrease_weight else "None"
    )

    return f"""# Comparative Metric Validation Report

**Generated**: {report.generated_at.isoformat()}
**Period**: {report.period_start} to {report.period_end}
**Metrics Tested**: {len(report.metrics_tested)}

---

## Executive Summary

| Metric | Sharpe | Win Rate | Effect (d) | Significant | Stable | Rec |
|--------|--------|----------|------------|-------------|--------|-----|
{summary_table}

### Legend
- **Significant**: p < 0.05 (statistically different from random)
- **Stable**: CV std < 0.5 (consistent across time periods)
- **Rec**: 📈 Increase | ➡️ Maintain | 📉 Decrease

---

## Rankings

### By Sharpe Ratio (Risk-Adjusted Returns)

| Rank | Metric | Sharpe Ratio |
|------|--------|--------------|
{sharpe_table}

### By Win Rate (Directional Accuracy)

| Rank | Metric | Win Rate |
|------|--------|----------|
{winrate_table}

### By Effect Size (Cohen's d)

| Rank | Metric | Cohen's d |
|------|--------|-----------|
{effect_table}

---

## Recommendations

### 📈 Increase Weight
{increase_list}

These metrics show statistically significant predictive power with stable performance.
Consider increasing their weight in the fusion model.

### ➡️ Maintain Weight
{maintain_list}

These metrics perform at baseline level or have inconclusive results.
Maintain current weights pending further data.

### 📉 Decrease Weight
{decrease_list}

These metrics underperform baselines or show unstable performance.
Consider reducing their weight or removing from the fusion model.

---

## Methodology

### Validation Process
1. **Performance Calculation**: Sharpe ratio, Sortino ratio, max drawdown, win rate
2. **Random Baseline**: 1000 Monte Carlo trials with shuffled signals
3. **Buy-and-Hold Baseline**: Passive market exposure comparison
4. **Statistical Significance**: One-sample t-test vs random baseline
5. **Effect Size**: Cohen's d (practical significance)
6. **Cross-Validation**: 3-fold time series split for consistency

### Interpretation Guidelines
- **Sharpe > 0.5**: Good risk-adjusted performance
- **Sharpe > 1.5**: Excellent risk-adjusted performance
- **p < 0.05**: Statistically significant
- **|d| > 0.2**: Small effect, **> 0.5**: Medium, **> 0.8**: Large
- **CV std < 0.5**: Stable across time periods

---

*Report generated by UTXOracle Metric Validator*
"""
