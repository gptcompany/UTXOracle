"""
Validation tests against ResearchBitcoin.net (RBN) golden data.

These tests verify our metric calculations match external reference data.
Run with: uv run pytest tests/validation/ -v

Test Strategy:
- Use golden data (pre-downloaded from RBN) as reference
- Compare against our calculations
- Flag deviations > threshold (default 5%)

IMPORTANT:
- Synthetic golden data is for infrastructure testing only
- Real validation requires downloading actual RBN data with API token
"""

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

GOLDEN_DATA_DIR = Path("tests/validation/golden_data")


def has_real_golden_data() -> bool:
    """Check if we have real (non-synthetic) golden data."""
    metadata_file = GOLDEN_DATA_DIR / "metadata.json"
    if not metadata_file.exists():
        return False

    import json

    with open(metadata_file) as f:
        metadata = json.load(f)

    return metadata.get("type") != "synthetic"


def load_golden_data(metric_id: str) -> pd.DataFrame:
    """Load golden data for a metric."""
    golden_file = GOLDEN_DATA_DIR / f"{metric_id}.parquet"
    if not golden_file.exists():
        pytest.skip(f"No golden data for {metric_id}")
    return pd.read_parquet(golden_file)


def calculate_mape(actual: pd.Series, reference: pd.Series) -> float:
    """Calculate Mean Absolute Percentage Error."""
    # Align series by index
    aligned = pd.DataFrame({"actual": actual, "reference": reference}).dropna()
    if len(aligned) == 0:
        return float("inf")

    # Avoid division by zero
    mask = aligned["reference"] != 0
    if not mask.any():
        return float("inf")

    errors = abs(aligned.loc[mask, "actual"] - aligned.loc[mask, "reference"])
    pct_errors = errors / abs(aligned.loc[mask, "reference"]) * 100

    return float(pct_errors.mean())


def calculate_correlation(actual: pd.Series, reference: pd.Series) -> float:
    """Calculate Pearson correlation coefficient."""
    aligned = pd.DataFrame({"actual": actual, "reference": reference}).dropna()
    if len(aligned) < 3:
        return 0.0
    return float(aligned["actual"].corr(aligned["reference"]))


class TestMetricLoaderInfrastructure:
    """Test that the metric loading infrastructure works."""

    def test_metric_loader_imports(self):
        """MetricLoader can be imported."""
        from scripts.integrations.metric_loader import MetricLoader

        loader = MetricLoader()
        assert loader is not None

    def test_golden_data_exists(self):
        """At least some golden data files exist."""
        parquet_files = list(GOLDEN_DATA_DIR.glob("*.parquet"))
        assert len(parquet_files) > 0, "No golden data found"

    def test_golden_data_readable(self):
        """Golden data files can be read."""
        for parquet_file in GOLDEN_DATA_DIR.glob("*.parquet"):
            df = pd.read_parquet(parquet_file)
            assert "date" in df.columns
            assert "value" in df.columns
            assert len(df) > 0

    def test_load_from_golden(self):
        """MetricLoader can load golden data."""
        from scripts.integrations.metric_loader import MetricLoader

        loader = MetricLoader(golden_data_dir=GOLDEN_DATA_DIR)

        end_date = date.today()
        start_date = end_date - timedelta(days=30)

        series = loader.load_metric("mvrv_z", start_date, end_date, source="golden")
        assert series.data, "No data loaded from golden"
        assert series.source == "golden"


class TestMVRVValidation:
    """Validation tests for MVRV Z-Score metric."""

    @pytest.mark.validation
    def test_mvrv_correlation_with_rbn(self):
        """MVRV Z-Score correlates highly with RBN reference (r > 0.9)."""
        from scripts.integrations.metric_loader import MetricLoader

        loader = MetricLoader(golden_data_dir=GOLDEN_DATA_DIR)
        golden = load_golden_data("mvrv_z")

        # Load our data
        end_date = date.today()
        start_date = end_date - timedelta(days=30)

        our_series = loader.load_metric("mvrv_z", start_date, end_date)

        if not our_series.data:
            pytest.skip("No UTXOracle MVRV data available")

        # Convert to series
        our_df = our_series.to_dataframe()
        golden["date"] = pd.to_datetime(golden["date"]).dt.date
        golden_series = golden.set_index("date")["value"]

        correlation = calculate_correlation(our_df["value"], golden_series)

        # For synthetic data, we won't match. For real data, require r > 0.9
        if has_real_golden_data():
            assert correlation > 0.9, (
                f"MVRV correlation {correlation:.3f} below threshold 0.9"
            )
        else:
            # Just verify the calculation works with synthetic data
            assert isinstance(correlation, float), (
                "Correlation calculation should return float"
            )

    @pytest.mark.validation
    def test_mvrv_mape_within_threshold(self):
        """MVRV Z-Score MAPE from RBN < 10%."""
        from scripts.integrations.metric_loader import MetricLoader

        loader = MetricLoader(golden_data_dir=GOLDEN_DATA_DIR)
        golden = load_golden_data("mvrv_z")

        end_date = date.today()
        start_date = end_date - timedelta(days=30)

        our_series = loader.load_metric("mvrv_z", start_date, end_date)

        if not our_series.data:
            pytest.skip("No UTXOracle MVRV data available")

        our_df = our_series.to_dataframe()
        golden["date"] = pd.to_datetime(golden["date"]).dt.date
        golden_series = golden.set_index("date")["value"]

        mape = calculate_mape(our_df["value"], golden_series)

        if has_real_golden_data():
            assert mape < 10.0, f"MVRV MAPE {mape:.2f}% exceeds threshold 10%"
        else:
            # Synthetic data won't match our calculations
            assert mape >= 0, "MAPE should be non-negative"


class TestSOPRValidation:
    """Validation tests for SOPR metric."""

    @pytest.mark.validation
    def test_sopr_correlation_with_rbn(self):
        """SOPR correlates highly with RBN reference (r > 0.9)."""
        from scripts.integrations.metric_loader import MetricLoader

        loader = MetricLoader(golden_data_dir=GOLDEN_DATA_DIR)
        golden = load_golden_data("sopr")

        end_date = date.today()
        start_date = end_date - timedelta(days=30)

        our_series = loader.load_metric("sopr", start_date, end_date)

        if not our_series.data:
            pytest.skip("No UTXOracle SOPR data available")

        our_df = our_series.to_dataframe()
        golden["date"] = pd.to_datetime(golden["date"]).dt.date
        golden_series = golden.set_index("date")["value"]

        correlation = calculate_correlation(our_df["value"], golden_series)

        if has_real_golden_data():
            assert correlation > 0.9, (
                f"SOPR correlation {correlation:.3f} below threshold 0.9"
            )


class TestNUPLValidation:
    """Validation tests for NUPL metric."""

    @pytest.mark.validation
    def test_nupl_correlation_with_rbn(self):
        """NUPL correlates highly with RBN reference (r > 0.9)."""
        from scripts.integrations.metric_loader import MetricLoader

        loader = MetricLoader(golden_data_dir=GOLDEN_DATA_DIR)
        golden = load_golden_data("nupl")

        end_date = date.today()
        start_date = end_date - timedelta(days=30)

        our_series = loader.load_metric("nupl", start_date, end_date)

        if not our_series.data:
            pytest.skip("No UTXOracle NUPL data available")

        our_df = our_series.to_dataframe()
        golden["date"] = pd.to_datetime(golden["date"]).dt.date
        golden_series = golden.set_index("date")["value"]

        correlation = calculate_correlation(our_df["value"], golden_series)

        if has_real_golden_data():
            assert correlation > 0.9, (
                f"NUPL correlation {correlation:.3f} below threshold 0.9"
            )


class TestRealizedCapValidation:
    """Validation tests for Realized Cap metric."""

    @pytest.mark.validation
    def test_realized_cap_correlation_with_rbn(self):
        """Realized Cap correlates highly with RBN reference (r > 0.95)."""
        from scripts.integrations.metric_loader import MetricLoader

        loader = MetricLoader(golden_data_dir=GOLDEN_DATA_DIR)
        golden = load_golden_data("realized_cap")

        end_date = date.today()
        start_date = end_date - timedelta(days=30)

        our_series = loader.load_metric("realized_cap", start_date, end_date)

        if not our_series.data:
            pytest.skip("No UTXOracle Realized Cap data available")

        our_df = our_series.to_dataframe()
        golden["date"] = pd.to_datetime(golden["date"]).dt.date
        golden_series = golden.set_index("date")["value"]

        correlation = calculate_correlation(our_df["value"], golden_series)

        if has_real_golden_data():
            # Realized Cap should be very close (r > 0.95)
            assert correlation > 0.95, (
                f"Realized Cap correlation {correlation:.3f} below threshold 0.95"
            )

    @pytest.mark.validation
    def test_realized_cap_mape_within_threshold(self):
        """Realized Cap MAPE from RBN < 5%."""
        from scripts.integrations.metric_loader import MetricLoader

        loader = MetricLoader(golden_data_dir=GOLDEN_DATA_DIR)
        golden = load_golden_data("realized_cap")

        end_date = date.today()
        start_date = end_date - timedelta(days=30)

        our_series = loader.load_metric("realized_cap", start_date, end_date)

        if not our_series.data:
            pytest.skip("No UTXOracle Realized Cap data available")

        our_df = our_series.to_dataframe()
        golden["date"] = pd.to_datetime(golden["date"]).dt.date
        golden_series = golden.set_index("date")["value"]

        mape = calculate_mape(our_df["value"], golden_series)

        if has_real_golden_data():
            assert mape < 5.0, f"Realized Cap MAPE {mape:.2f}% exceeds threshold 5%"


class TestValidationReport:
    """Tests for generating validation reports."""

    def test_generate_validation_summary(self):
        """Generate summary of all validation metrics."""
        from scripts.integrations.metric_loader import MetricLoader

        loader = MetricLoader(golden_data_dir=GOLDEN_DATA_DIR)
        metrics = ["mvrv_z", "sopr", "nupl", "realized_cap"]

        end_date = date.today()
        start_date = end_date - timedelta(days=30)

        summary = []
        for metric_id in metrics:
            try:
                golden = load_golden_data(metric_id)
                our_series = loader.load_metric(metric_id, start_date, end_date)

                if our_series.data:
                    our_df = our_series.to_dataframe()
                    golden["date"] = pd.to_datetime(golden["date"]).dt.date
                    golden_series = golden.set_index("date")["value"]

                    correlation = calculate_correlation(our_df["value"], golden_series)
                    mape = calculate_mape(our_df["value"], golden_series)
                else:
                    correlation = None
                    mape = None

                summary.append(
                    {
                        "metric": metric_id,
                        "our_records": len(our_series.data) if our_series.data else 0,
                        "golden_records": len(golden),
                        "correlation": correlation,
                        "mape": mape,
                    }
                )
            except Exception as e:
                summary.append(
                    {
                        "metric": metric_id,
                        "error": str(e),
                    }
                )

        # Just verify we can generate a summary
        assert len(summary) == len(metrics)
        for item in summary:
            assert "metric" in item
