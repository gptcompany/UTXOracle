# Spec-035: ResearchBitcoin.net API Integration

## Overview

Create a lightweight integration layer to fetch metrics from ResearchBitcoin.net (RBN) for comparison, validation, and gap-filling. RBN provides 300+ free metrics - we integrate selectively.

## Problem Statement

UTXOracle calculates metrics independently from blockchain data. RBN provides:
1. **Validation**: Compare our calculations against theirs
2. **Gap-filling**: Metrics we haven't implemented yet
3. **Research**: Access to proprietary indicators (PRO Risk)

## API Discovery

RBN provides a documented REST API with OpenAPI/Swagger specification:
```
Base URL: https://api.researchbitcoin.net/v1
Swagger: /v1/swagger.json
```

**Authentication**: Token-based via query parameter (`?token=UUID`)

**Tier Limits**:
| Tier | Weekly Queries | History |
|------|----------------|---------|
| 0 (Free) | 100 | 1 year |
| 1 | 300 | Full |
| 2 | 10,000 | Full |

**Note**: Frontend uses Dash (Plotly), not Shiny. See `research.md` for full API discovery.

## Technical Design

### Integration Strategy

```python
from enum import Enum
from dataclasses import dataclass
from typing import Optional
import httpx

class RBNMetricCategory(Enum):
    ONCHAIN = "onchain"
    DERIVATIVES = "derivatives"
    MINING = "mining"
    SENTIMENT = "sentiment"
    PROPRIETARY = "proprietary"

@dataclass
class RBNMetric:
    name: str
    category: RBNMetricCategory
    description: str
    utxoracle_equivalent: Optional[str]  # Our spec number if we have it
    update_frequency: str  # "daily", "hourly", "block"
    is_free: bool

# Known RBN metrics with UTXOracle equivalents
RBN_METRIC_MAPPING = {
    "mvrv_z_score": RBNMetric(
        name="MVRV Z-Score",
        category=RBNMetricCategory.ONCHAIN,
        description="Market Value to Realized Value Z-Score",
        utxoracle_equivalent="spec-007",
        update_frequency="daily",
        is_free=True
    ),
    "sopr": RBNMetric(
        name="SOPR",
        category=RBNMetricCategory.ONCHAIN,
        description="Spent Output Profit Ratio",
        utxoracle_equivalent="spec-016",
        update_frequency="daily",
        is_free=True
    ),
    "pro_risk": RBNMetric(
        name="PRO Risk Metric",
        category=RBNMetricCategory.PROPRIETARY,
        description="Composite cycle position indicator",
        utxoracle_equivalent="spec-033",  # Our implementation
        update_frequency="daily",
        is_free=False  # Subscription required
    ),
    # ... 300+ more metrics
}
```

### Fetcher Implementation

```python
class RBNFetcher:
    """Fetch metrics from ResearchBitcoin.net."""

    BASE_URL = "https://researchbitcoin.net"
    TIMEOUT = 30.0

    def __init__(self, cache_dir: Path = Path("cache/rbn")):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.client = httpx.Client(timeout=self.TIMEOUT)

    async def fetch_metric(
        self,
        metric_id: str,
        start_date: date,
        end_date: date
    ) -> pd.DataFrame:
        """Fetch metric data for date range."""
        cache_key = f"{metric_id}_{start_date}_{end_date}.parquet"
        cache_path = self.cache_dir / cache_key

        if cache_path.exists():
            return pd.read_parquet(cache_path)

        # Try known endpoints (discovered via inspection)
        data = await self._fetch_from_shiny(metric_id, start_date, end_date)

        if data is not None:
            data.to_parquet(cache_path)

        return data

    async def _fetch_from_shiny(
        self,
        metric_id: str,
        start_date: date,
        end_date: date
    ) -> Optional[pd.DataFrame]:
        """Attempt to fetch from Shiny backend."""
        # Implementation depends on reverse-engineering RBN's API
        # This is a placeholder for the actual integration
        raise NotImplementedError("RBN API discovery in progress")
```

### Comparison Service

```python
@dataclass
class MetricComparison:
    metric_name: str
    date: date
    utxoracle_value: float
    rbn_value: float
    absolute_diff: float
    relative_diff_pct: float
    status: str  # "match", "minor_diff", "major_diff", "missing"

class ValidationService:
    """Compare UTXOracle metrics against RBN."""

    def compare_metric(
        self,
        metric_id: str,
        date_range: tuple[date, date]
    ) -> list[MetricComparison]:
        """Compare our metric values against RBN."""
        our_data = self.load_utxoracle_metric(metric_id, date_range)
        rbn_data = self.fetcher.fetch_metric(metric_id, *date_range)

        comparisons = []
        for d in our_data.index:
            if d in rbn_data.index:
                our_val = our_data.loc[d]
                rbn_val = rbn_data.loc[d]
                abs_diff = abs(our_val - rbn_val)
                rel_diff = (abs_diff / rbn_val) * 100 if rbn_val != 0 else float('inf')

                status = "match" if rel_diff < 1 else "minor_diff" if rel_diff < 5 else "major_diff"

                comparisons.append(MetricComparison(
                    metric_name=metric_id,
                    date=d,
                    utxoracle_value=our_val,
                    rbn_value=rbn_val,
                    absolute_diff=abs_diff,
                    relative_diff_pct=rel_diff,
                    status=status
                ))

        return comparisons

    def generate_report(
        self,
        comparisons: list[MetricComparison]
    ) -> str:
        """Generate validation report."""
        matches = sum(1 for c in comparisons if c.status == "match")
        total = len(comparisons)
        return f"Validation: {matches}/{total} ({matches/total*100:.1f}%) within 1% tolerance"
```

## Metrics to Integrate

### Priority 1: Validation (we have these)
- MVRV Z-Score → spec-007
- SOPR → spec-016
- NUPL → spec-007
- Reserve Risk → spec-018
- Realized Cap → spec-007

### Priority 2: Gap-filling (we don't have)
- Thermocap Multiple
- CVDD (Cumulative Value Days Destroyed)
- Stock-to-Flow variants
- Pi Cycle Top indicator
- 200-week SMA heatmap

### Priority 3: Proprietary (paid/complex)
- PRO Risk Metric → spec-033 (our implementation)
- Entity-adjusted metrics

## API Endpoints

```
GET /api/v1/validation/rbn/{metric_id}
GET /api/v1/validation/rbn/report

Response:
{
    "metric": "mvrv_z_score",
    "date_range": ["2024-01-01", "2025-12-25"],
    "comparisons": 720,
    "matches": 695,
    "match_rate": 96.5,
    "avg_deviation_pct": 0.8
}
```

## Caching Strategy

- Cache RBN data for 24 hours
- Store in `cache/rbn/*.parquet`
- Invalidate on manual refresh

## Implementation Files

```
scripts/integrations/rbn_fetcher.py   # Data fetcher
scripts/integrations/rbn_validator.py # Comparison logic
api/routes/validation.py              # API endpoints
tests/test_rbn_integration.py         # Tests
cache/rbn/                            # Data cache
```

## Legal Considerations

1. **Terms of Service**: Review RBN ToS before scraping
2. **Rate limiting**: Respect server limits (max 1 req/sec)
3. **Attribution**: Credit RBN in any public comparisons
4. **Fair use**: For validation only, not redistribution

## Estimated Effort

- API discovery: 1-2 hours
- Fetcher implementation: 1 hour
- Validation service: 1 hour
- Total: 3-4 hours

## Status

**Draft** - Awaiting implementation approval
