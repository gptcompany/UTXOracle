"""
Unified Metric Loader for UTXOracle validation system.

Loads metric data from multiple sources:
1. DuckDB tables (primary)
2. Calculated on-demand from UTXO data (fallback)
3. Cached golden data (for tests)

Supports P1 metrics: MVRV, SOPR, NUPL, Realized Cap
"""

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Database path
DEFAULT_DB_PATH = Path(
    "/media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db"
)
GOLDEN_DATA_DIR = Path("tests/validation/golden_data")


@dataclass
class MetricDataPoint:
    """Single metric observation."""

    date: date
    value: float
    source: str  # "duckdb", "calculated", "golden"


@dataclass
class MetricSeries:
    """Time series of metric observations."""

    metric_id: str
    data: list[MetricDataPoint]
    start_date: date
    end_date: date
    source: str

    def to_dict(self) -> dict[date, float]:
        """Convert to date->value dictionary."""
        return {dp.date: dp.value for dp in self.data}

    def to_dataframe(self) -> pd.DataFrame:
        """Convert to pandas DataFrame."""
        return pd.DataFrame(
            [(dp.date, dp.value) for dp in self.data], columns=["date", "value"]
        ).set_index("date")


# Metric configurations: how to load each metric
METRIC_CONFIG = {
    # MVRV Z-Score (spec-007)
    "mvrv_z": {
        "table": "cointime_metrics",
        "column": "aviv_ratio",  # AVIV is our MVRV variant
        "fallback_table": "metrics",
        "fallback_column": None,  # Not stored yet
        "transform": None,
    },
    # SOPR (spec-016)
    "sopr": {
        "table": "sopr_metrics",
        "column": "aggregate_sopr",
        "fallback_table": None,
        "transform": None,
    },
    # NUPL (spec-007)
    "nupl": {
        "table": "nupl_metrics",
        "column": "nupl",
        "fallback_table": "metrics",
        "fallback_column": None,
        "transform": None,
    },
    # Realized Cap (spec-007)
    "realized_cap": {
        "table": "realized_metrics",
        "column": "realized_cap_usd",
        "fallback_table": None,
        "transform": None,
    },
    # Liveliness (spec-018)
    "liveliness": {
        "table": "cointime_metrics",
        "column": "liveliness",
        "fallback_table": None,
        "transform": None,
    },
    # Power Law price (spec-034)
    "power_law": {
        "table": "price_models",
        "column": "power_law_price",
        "fallback_table": None,
        "transform": None,
    },
}


class MetricLoader:
    """
    Unified metric loader for UTXOracle data.

    Supports multiple data sources with graceful fallbacks.
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        golden_data_dir: Optional[Path] = None,
    ):
        """
        Initialize metric loader.

        Args:
            db_path: Path to DuckDB database
            golden_data_dir: Directory containing golden test data
        """
        self.db_path = db_path or DEFAULT_DB_PATH
        self.golden_data_dir = golden_data_dir or GOLDEN_DATA_DIR

    def _get_connection(self):
        """Get DuckDB connection."""
        try:
            import duckdb

            if not self.db_path.exists():
                logger.warning(f"Database not found: {self.db_path}")
                return None
            return duckdb.connect(str(self.db_path), read_only=True)
        except ImportError:
            logger.error("DuckDB not installed")
            return None

    def load_metric(
        self,
        metric_id: str,
        start_date: date,
        end_date: Optional[date] = None,
        source: str = "auto",
    ) -> MetricSeries:
        """
        Load metric data for date range.

        Args:
            metric_id: Metric identifier (e.g., 'mvrv_z', 'sopr')
            start_date: Start date
            end_date: End date (defaults to today)
            source: Data source ("duckdb", "golden", "auto")

        Returns:
            MetricSeries with data points

        Raises:
            ValueError: If metric_id not supported
        """
        end_date = end_date or date.today()

        if metric_id not in METRIC_CONFIG:
            raise ValueError(f"Unsupported metric: {metric_id}")

        # Try sources in order based on preference
        if source == "golden":
            return self._load_from_golden(metric_id, start_date, end_date)

        if source == "duckdb":
            return self._load_from_duckdb(metric_id, start_date, end_date)

        # Auto: try DuckDB first, fall back to golden
        try:
            result = self._load_from_duckdb(metric_id, start_date, end_date)
            if result.data:
                return result
        except Exception as e:
            logger.warning(f"DuckDB load failed for {metric_id}: {e}")

        # Fall back to golden data
        return self._load_from_golden(metric_id, start_date, end_date)

    def _load_from_duckdb(
        self,
        metric_id: str,
        start_date: date,
        end_date: date,
    ) -> MetricSeries:
        """Load metric from DuckDB."""
        config = METRIC_CONFIG[metric_id]
        conn = self._get_connection()

        if conn is None:
            return MetricSeries(
                metric_id=metric_id,
                data=[],
                start_date=start_date,
                end_date=end_date,
                source="duckdb",
            )

        table = config["table"]
        column = config["column"]

        # Try to determine date/timestamp column
        try:
            # Check table schema
            schema = conn.execute(f"DESCRIBE {table}").fetchall()
            schema_cols = [col[0] for col in schema]

            if "date" in schema_cols:
                date_col = "date"
            elif "timestamp" in schema_cols:
                date_col = "timestamp"
            elif "block_height" in schema_cols:
                # For block-based tables, join with block_info or use timestamp
                date_col = "timestamp"
            else:
                logger.warning(f"No date column found in {table}")
                conn.close()
                return MetricSeries(
                    metric_id=metric_id,
                    data=[],
                    start_date=start_date,
                    end_date=end_date,
                    source="duckdb",
                )

            # Query data
            query = f"""
                SELECT DATE({date_col}) as dt, {column} as val
                FROM {table}
                WHERE DATE({date_col}) >= ? AND DATE({date_col}) <= ?
                ORDER BY {date_col}
            """
            result = conn.execute(query, [start_date, end_date]).fetchall()
            conn.close()

            data_points = []
            for row in result:
                dt, val = row
                if val is not None:
                    data_points.append(
                        MetricDataPoint(
                            date=dt if isinstance(dt, date) else dt.date(),
                            value=float(val),
                            source="duckdb",
                        )
                    )

            return MetricSeries(
                metric_id=metric_id,
                data=data_points,
                start_date=start_date,
                end_date=end_date,
                source="duckdb",
            )

        except Exception as e:
            logger.error(f"Error loading {metric_id} from DuckDB: {e}")
            if conn:
                conn.close()
            return MetricSeries(
                metric_id=metric_id,
                data=[],
                start_date=start_date,
                end_date=end_date,
                source="duckdb",
            )

    def _load_from_golden(
        self,
        metric_id: str,
        start_date: date,
        end_date: date,
    ) -> MetricSeries:
        """Load metric from golden test data (Parquet files)."""
        golden_file = self.golden_data_dir / f"{metric_id}.parquet"

        if not golden_file.exists():
            logger.warning(f"Golden data not found: {golden_file}")
            return MetricSeries(
                metric_id=metric_id,
                data=[],
                start_date=start_date,
                end_date=end_date,
                source="golden",
            )

        df = pd.read_parquet(golden_file)

        # Ensure date column is date type
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.date
        elif df.index.name == "date":
            df = df.reset_index()
            df["date"] = pd.to_datetime(df["date"]).dt.date

        # Filter by date range
        mask = (df["date"] >= start_date) & (df["date"] <= end_date)
        df = df[mask]

        # Get value column
        value_col = "value" if "value" in df.columns else df.columns[1]

        data_points = [
            MetricDataPoint(
                date=row["date"],
                value=float(row[value_col]),
                source="golden",
            )
            for _, row in df.iterrows()
        ]

        return MetricSeries(
            metric_id=metric_id,
            data=data_points,
            start_date=start_date,
            end_date=end_date,
            source="golden",
        )

    def list_available_metrics(self) -> list[str]:
        """Return list of supported metric IDs."""
        return list(METRIC_CONFIG.keys())

    def check_data_availability(
        self, metric_id: str, start_date: date, end_date: date
    ) -> dict:
        """
        Check data availability for a metric.

        Returns:
            Dict with 'duckdb_count', 'golden_count', 'coverage_pct'
        """
        days_requested = (end_date - start_date).days + 1

        # Check DuckDB
        try:
            duckdb_data = self._load_from_duckdb(metric_id, start_date, end_date)
            duckdb_count = len(duckdb_data.data)
        except Exception:
            duckdb_count = 0

        # Check golden
        golden_data = self._load_from_golden(metric_id, start_date, end_date)
        golden_count = len(golden_data.data)

        return {
            "metric_id": metric_id,
            "days_requested": days_requested,
            "duckdb_count": duckdb_count,
            "golden_count": golden_count,
            "coverage_pct": max(duckdb_count, golden_count) / days_requested * 100
            if days_requested > 0
            else 0,
        }
