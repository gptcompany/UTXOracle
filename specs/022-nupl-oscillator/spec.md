# spec-022: NUPL Oscillator

## Overview
Net Unrealized Profit/Loss oscillator - core CheckOnChain metric.

## Formula
```
NUPL = (Market Cap - Realized Cap) / Market Cap
     = 1 - (Realized Cap / Market Cap)
```

## Signal Zones
| Zone | NUPL Range | Interpretation |
|------|------------|----------------|
| CAPITULATION | < 0 | Underwater, extreme fear |
| HOPE/FEAR | 0 - 0.25 | Recovery phase |
| OPTIMISM | 0.25 - 0.5 | Bull market building |
| BELIEF | 0.5 - 0.75 | Strong conviction |
| EUPHORIA | > 0.75 | Extreme greed, top signal |

## Implementation

### Data Source
- `realized_cap` from `scripts/metrics/realized_metrics.py`
- `market_cap` = current_price × circulating_supply

### Files
- `scripts/metrics/nupl.py` - Calculator
- `tests/test_nupl.py` - TDD tests
- `scripts/models/metrics_models.py` - Add NUPLResult dataclass

### API
- `GET /api/metrics/nupl` - Returns NUPL with zone classification

## Effort: 1-2 hours
## Evidence Grade: A (Glassnode core metric)
## ROI: Maximum - completes profit/loss metric suite
