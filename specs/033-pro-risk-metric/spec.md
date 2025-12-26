# Spec-033: PRO Risk Metric Implementation

## Overview

Implement a composite risk metric inspired by ResearchBitcoin.net's proprietary "PRO Risk Metric" - a 0-1 scale cycle position indicator that aggregates multiple on-chain signals.

## Problem Statement

UTXOracle currently produces individual metrics without a unified risk signal. A composite metric combining multiple indicators would provide:
- Single-glance market cycle position
- Actionable buy/sell zones (0.0-0.2 = oversold, 0.8-1.0 = overbought)
- Historical validation against known cycle tops/bottoms

## Technical Design

### Input Signals (Weighted)

| Metric | Weight | Source | Evidence Grade |
|--------|--------|--------|----------------|
| MVRV Z-Score | 30% | spec-007 | A |
| SOPR | 20% | spec-016 | A |
| NUPL | 20% | spec-007 | A |
| Reserve Risk | 15% | spec-018 (cointime) | B |
| Puell Multiple | 10% | miners/daily_revenue | B |
| Realized Cap HODL Waves | 5% | spec-017 | B |

*Note: Weights refined during research phase to align with evidence grades (Grade A: 70% total, Grade B: 30% total).*

### Normalization Strategy

Each metric normalized to 0-1 using historical percentile ranking:
```python
def normalize_metric(value: float, historical_data: list[float]) -> float:
    """Convert raw metric to 0-1 percentile score."""
    return sum(1 for h in historical_data if h <= value) / len(historical_data)
```

### Composite Calculation

```python
@dataclass
class ProRiskMetric:
    timestamp: datetime
    value: float  # 0.0 - 1.0
    zone: str     # "extreme_fear", "fear", "neutral", "greed", "extreme_greed"
    components: dict[str, float]  # Individual normalized scores
    confidence: float  # Based on data availability

def calculate_pro_risk(
    mvrv_z: float,
    sopr: float,
    reserve_risk: float,
    puell: float,
    nupl: float,
    hodl_waves: float,
    historical_percentiles: dict[str, list[float]]
) -> ProRiskMetric:
    weights = {
        "mvrv_z": 0.30,
        "sopr": 0.20,
        "nupl": 0.20,
        "reserve_risk": 0.15,
        "puell": 0.10,
        "hodl_waves": 0.05
    }

    components = {
        "mvrv_z": normalize_metric(mvrv_z, historical_percentiles["mvrv_z"]),
        "sopr": normalize_metric(sopr, historical_percentiles["sopr"]),
        # ... etc
    }

    weighted_sum = sum(
        components[k] * weights[k] for k in weights
    )

    return ProRiskMetric(
        timestamp=datetime.utcnow(),
        value=weighted_sum,
        zone=classify_zone(weighted_sum),
        components=components,
        confidence=calculate_confidence(components)
    )
```

### Zone Classification

| Value Range | Zone | Interpretation |
|-------------|------|----------------|
| 0.00 - 0.20 | extreme_fear | Strong buy signal |
| 0.20 - 0.40 | fear | Accumulation zone |
| 0.40 - 0.60 | neutral | Hold/DCA |
| 0.60 - 0.80 | greed | Caution zone |
| 0.80 - 1.00 | extreme_greed | Distribution zone |

## API Endpoint

```
GET /api/v1/risk/pro
Response:
{
    "timestamp": "2025-12-25T12:00:00Z",
    "value": 0.62,
    "zone": "greed",
    "components": {
        "mvrv_z": 0.71,
        "sopr": 0.55,
        "reserve_risk": 0.68,
        "puell": 0.58,
        "nupl": 0.63,
        "hodl_waves": 0.45
    },
    "confidence": 0.95,
    "historical_context": {
        "percentile_30d": 0.78,
        "percentile_1y": 0.65
    }
}
```

## Data Requirements

1. **Historical percentile data**: Minimum 4 years for accurate normalization (returns 0.5 neutral if insufficient)
2. **Real-time inputs**: All component metrics from existing specs (daily batch, not real-time streaming)
3. **Update frequency**: Daily (aligned with UTXOracle daily calculation)

## Implementation Files

```
scripts/metrics/pro_risk.py          # Core calculation
scripts/metrics/puell_multiple.py    # Puell Multiple (new)
scripts/metrics/init_risk_db.py      # DuckDB schema setup
api/routes/risk.py                   # API endpoint
api/models/risk_models.py            # Pydantic models
tests/test_pro_risk.py               # Unit tests
tests/test_api_risk.py               # API tests
```

*Note: Storage uses DuckDB tables (`risk_percentiles`, `pro_risk_daily`) per research decision for efficient range queries.*

## Validation Criteria

1. **Backtest correlation**: Compare against BTC price cycle tops/bottoms (2017, 2021, 2022) - expect >0.8 in extreme zones
2. **RBN comparison**: Should produce values within ±5% deviation when both have same inputs
3. **No lookahead bias**: Only uses data available at calculation time - verified via walk-forward backtest

## Estimated Effort

- Implementation: 4-5 hours
- Testing & validation: 2-3 hours
- Total: 6-8 hours

## Dependencies

- spec-007 (metrics base)
- spec-016 (SOPR)
- spec-017 (UTXO lifecycle)
- spec-018 (cointime)

## Status

**Draft** - Awaiting implementation approval
