"""Core validation logic for metric comparison.

Compares UTXOracle API responses with reference baselines.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx


@dataclass
class ValidationResult:
    """Result of a single metric validation."""

    metric: str
    timestamp: datetime
    our_value: float
    reference_value: float
    deviation_pct: float
    tolerance_pct: float
    status: str  # PASS, FAIL, WARN
    notes: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "metric": self.metric,
            "timestamp": self.timestamp.isoformat(),
            "our_value": self.our_value,
            "reference_value": self.reference_value,
            "deviation_pct": round(self.deviation_pct, 4),
            "tolerance_pct": self.tolerance_pct,
            "status": self.status,
            "notes": self.notes,
        }


class MetricValidator:
    """Validates UTXOracle metrics against reference data."""

    # Default tolerances by metric
    TOLERANCES = {
        "mvrv_z": 2.0,
        "nupl": 2.0,
        "sopr": 1.0,
        "sth_sopr": 2.0,
        "lth_sopr": 2.0,
        "cdd": 5.0,
        "binary_cdd": 0.0,  # Boolean - must match
        "cost_basis": 2.0,
        "hash_ribbons_30d": 3.0,
        "hash_ribbons_60d": 3.0,
        "net_realized_pnl": 5.0,
        "pl_ratio": 3.0,
    }

    def __init__(
        self,
        api_base_url: str = "http://localhost:8000",
        baselines_dir: Optional[Path] = None,
    ):
        self.api_base_url = api_base_url
        self.baselines_dir = baselines_dir or Path("validation/baselines")
        self.results: list[ValidationResult] = []

    def fetch_our_value(self, endpoint: str) -> dict:
        """Fetch metric value from our API."""
        url = f"{self.api_base_url}{endpoint}"
        response = httpx.get(url, timeout=30)
        response.raise_for_status()
        return response.json()

    def load_baseline(self, metric: str) -> dict:
        """Load reference baseline for a metric."""
        baseline_file = self.baselines_dir / f"{metric}_baseline.json"
        if not baseline_file.exists():
            raise FileNotFoundError(f"Baseline not found: {baseline_file}")
        with open(baseline_file) as f:
            return json.load(f)

    def compare(
        self,
        metric: str,
        our_value: float,
        reference_value: float,
        tolerance_pct: Optional[float] = None,
    ) -> ValidationResult:
        """Compare our value with reference."""
        if tolerance_pct is None:
            tolerance_pct = self.TOLERANCES.get(metric, 5.0)

        if reference_value == 0:
            deviation_pct = 0.0 if our_value == 0 else 100.0
        else:
            deviation_pct = (
                abs(our_value - reference_value) / abs(reference_value) * 100
            )

        if deviation_pct <= tolerance_pct:
            status = "PASS"
        elif deviation_pct <= tolerance_pct * 2:
            status = "WARN"
        else:
            status = "FAIL"

        result = ValidationResult(
            metric=metric,
            timestamp=datetime.utcnow(),
            our_value=our_value,
            reference_value=reference_value,
            deviation_pct=deviation_pct,
            tolerance_pct=tolerance_pct,
            status=status,
        )
        self.results.append(result)
        return result

    def validate_mvrv(self) -> ValidationResult:
        """Validate MVRV-Z Score."""
        # Fetch from our API
        try:
            data = self.fetch_our_value("/api/metrics/mvrv")
            our_value = data.get("mvrv_z_score", 0)
        except Exception as e:
            return ValidationResult(
                metric="mvrv_z",
                timestamp=datetime.utcnow(),
                our_value=0,
                reference_value=0,
                deviation_pct=100,
                tolerance_pct=2.0,
                status="ERROR",
                notes=str(e),
            )

        # Load baseline
        try:
            baseline = self.load_baseline("mvrv")
            reference_value = baseline.get("current", {}).get("mvrv_z_score", 0)
        except FileNotFoundError:
            reference_value = 0

        return self.compare("mvrv_z", our_value, reference_value)

    def validate_nupl(self) -> ValidationResult:
        """Validate NUPL."""
        try:
            data = self.fetch_our_value("/api/metrics/nupl")
            our_value = data.get("nupl", 0)
        except Exception as e:
            return ValidationResult(
                metric="nupl",
                timestamp=datetime.utcnow(),
                our_value=0,
                reference_value=0,
                deviation_pct=100,
                tolerance_pct=2.0,
                status="ERROR",
                notes=str(e),
            )

        try:
            baseline = self.load_baseline("nupl")
            reference_value = baseline.get("current", {}).get("nupl", 0)
        except FileNotFoundError:
            reference_value = 0

        return self.compare("nupl", our_value, reference_value)

    def validate_hash_ribbons(self) -> list[ValidationResult]:
        """Validate Hash Ribbons."""
        results = []
        try:
            data = self.fetch_our_value("/api/metrics/hash-ribbons")
            our_30d = data.get("hashrate_ma_30d", 0)
            our_60d = data.get("hashrate_ma_60d", 0)
        except Exception as e:
            return [
                ValidationResult(
                    metric="hash_ribbons",
                    timestamp=datetime.utcnow(),
                    our_value=0,
                    reference_value=0,
                    deviation_pct=100,
                    tolerance_pct=3.0,
                    status="ERROR",
                    notes=str(e),
                )
            ]

        try:
            baseline = self.load_baseline("hash_ribbons")
            ref_30d = baseline.get("current", {}).get("ma_30d", 0)
            ref_60d = baseline.get("current", {}).get("ma_60d", 0)
        except FileNotFoundError:
            ref_30d = ref_60d = 0

        results.append(self.compare("hash_ribbons_30d", our_30d, ref_30d))
        results.append(self.compare("hash_ribbons_60d", our_60d, ref_60d))
        return results

    def run_all(self) -> list[ValidationResult]:
        """Run all validations."""
        self.results = []

        self.validate_mvrv()
        self.validate_nupl()
        self.validate_hash_ribbons()

        return self.results

    def generate_report(self) -> str:
        """Generate markdown validation report."""
        passed = sum(1 for r in self.results if r.status == "PASS")
        warned = sum(1 for r in self.results if r.status == "WARN")
        failed = sum(1 for r in self.results if r.status == "FAIL")
        errors = sum(1 for r in self.results if r.status == "ERROR")

        report = f"""# Validation Report

**Generated**: {datetime.utcnow().isoformat()}

## Summary

| Status | Count |
|--------|-------|
| ✅ PASS | {passed} |
| ⚠️ WARN | {warned} |
| ❌ FAIL | {failed} |
| 🔴 ERROR | {errors} |

## Details

| Metric | Our Value | Reference | Deviation | Tolerance | Status |
|--------|-----------|-----------|-----------|-----------|--------|
"""
        for r in self.results:
            status_icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌", "ERROR": "🔴"}.get(
                r.status, "?"
            )
            report += f"| {r.metric} | {r.our_value:.4f} | {r.reference_value:.4f} | {r.deviation_pct:.2f}% | ±{r.tolerance_pct}% | {status_icon} |\n"

        return report
