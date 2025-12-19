# spec-032: Metrics Dashboard Pages

## Overview

Create dedicated Plotly.js chart pages for each on-chain metric, designed for visual validation against CheckOnChain.com reference charts.

## Purpose

1. **Visual Validation**: Side-by-side comparison with CheckOnChain
2. **User Dashboard**: Interactive metric visualization
3. **API Testing**: Validate backend endpoints work correctly

## API Endpoints Available

| Metric | Endpoint | CheckOnChain Equivalent |
|--------|----------|------------------------|
| NUPL | `/api/metrics/nupl` | btconchain/unrealised/nupl |
| MVRV | `/api/metrics/advanced` (mvrv_z) | btconchain/unrealised/mvrv_all |
| SOPR | `/api/metrics/advanced` (sopr) | btconchain/realised/sopr |
| Cost Basis | `/api/metrics/cost-basis` | btconchain/realised/realised_price |
| Binary CDD | `/api/metrics/binary-cdd` | btconchain/lifespan/cdd_all |
| Hash Ribbons | `/api/metrics/mining-pulse` | btconchain/mining/hashribbons |
| Exchange Netflow | `/api/metrics/exchange-netflow` | N/A (custom) |
| Wallet Waves | `/api/metrics/wallet-waves` | N/A (custom) |

**Note**: Chart pages require historical time series. Use `/history?days=365` variants where available:
- MVRV: `/api/metrics/wasserstein/history?days=365`
- Other metrics: Check if history endpoint exists, fallback to current value display

## Pages to Create

### Priority 1: Core Validation (CheckOnChain comparables)
1. **mvrv.html** - MVRV-Z Score with overbought/oversold zones
2. **nupl.html** - Net Unrealized P/L with zone coloring
3. **sopr.html** - SOPR with 1.0 reference line
4. **cost_basis.html** - Realized Price vs Market Price
5. **hash_ribbons.html** - 30d/60d MA with capitulation zones

### Priority 2: Additional Metrics
6. **binary_cdd.html** - CDD heatmap / signal
7. **wallet_waves.html** - Cohort distribution
8. **exchange_netflow.html** - Inflow/Outflow balance

## Technical Requirements

### Plotly.js Standards
- Use same styling as CheckOnChain (for comparison)
- Dark theme default
- Responsive layout
- Log scale option for price charts

### Chart Components
```javascript
// Standard chart config
const config = {
  responsive: true,
  displayModeBar: true,
  modeBarButtonsToRemove: ['lasso2d', 'select2d']
};

// Standard layout template
const layout = {
  template: 'plotly_dark',
  xaxis: { title: 'Date', type: 'date' },
  yaxis: { title: '<metric>' },
  margin: { l: 60, r: 40, t: 60, b: 40 }
};
```

### Zone Coloring (per CheckOnChain style)
| Metric | Zones |
|--------|-------|
| MVRV-Z | <0 green, 0-3 neutral, 3-7 yellow, >7 red |
| NUPL | <0 capitulation, 0-0.25 hope, 0.25-0.5 optimism, 0.5-0.75 belief, >0.75 euphoria |
| SOPR | <1 loss (red), >1 profit (green) |

## File Structure

```
frontend/
├── metrics/
│   ├── mvrv.html
│   ├── nupl.html
│   ├── sopr.html
│   ├── cost_basis.html
│   ├── hash_ribbons.html
│   ├── binary_cdd.html
│   ├── wallet_waves.html
│   └── exchange_netflow.html
├── js/
│   ├── metrics-common.js    # Shared utilities
│   └── chart-themes.js      # Plotly theme configs
└── css/
    └── metrics.css          # Metric page styling
```

## Success Criteria

| Criterion | Target |
|-----------|--------|
| Visual match | 90% trend alignment with CheckOnChain |
| API integration | All endpoints return valid data |
| Responsive | Works on mobile and desktop |
| Performance | Chart loads in < 2s |

## Dependencies

- Plotly.js 2.x (CDN)
- FastAPI backend running on port 8000
- No additional npm dependencies

## Implementation Notes

1. Start with MVRV page as template
2. Reuse common code in metrics-common.js
3. Test each page against CheckOnChain screenshot
4. Iterate until visual match is achieved
