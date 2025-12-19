# Research: Metrics Dashboard Pages

## 1. CheckOnChain Visual Analysis

**Source**: https://charts.checkonchain.com

### Chart Style Observations

| Element | CheckOnChain Style |
|---------|-------------------|
| Theme | Dark background (#1a1a2e or similar) |
| Grid | Subtle gray grid lines |
| Traces | Colored fills for zones, line plots for values |
| Price Overlay | Orange/yellow BTC price on secondary y-axis |
| Legend | Top or bottom, horizontal layout |
| Tooltips | Shows date + value on hover |
| Responsiveness | Full-width, scales to container |

### Zone Coloring Standards

**MVRV-Z Score**:
- < 0: Green (undervalued)
- 0-3: Neutral (gray/blue)
- 3-7: Yellow (caution)
- > 7: Red (overvalued)

**NUPL (Net Unrealized Profit/Loss)**:
- < 0: Red (Capitulation)
- 0-0.25: Orange (Hope/Fear)
- 0.25-0.5: Yellow (Optimism/Anxiety)
- 0.5-0.75: Light Green (Belief/Denial)
- > 0.75: Green (Euphoria/Greed)

**SOPR**:
- < 1: Red (selling at loss)
- = 1: White/neutral (break-even)
- > 1: Green (selling at profit)

### Plotly.js Implementation Notes

CheckOnChain uses Plotly.js with these patterns:
- `Plotly.newPlot(containerId, data, layout, config)`
- Traces use `fill: 'tozeroy'` for area charts
- Multiple y-axes for price overlay (`yaxis2`)
- Date range selector for time filtering

## 2. API Endpoints Analysis

### Available Endpoints (from api/main.py)

| Metric | Endpoint | Response Format |
|--------|----------|-----------------|
| MVRV-Z | `/api/metrics/advanced` | `{ mvrv_z, sopr, sthrp, lthrp, ... }` |
| NUPL | `/api/metrics/nupl` | `{ nupl, date, ... }` |
| SOPR | `/api/metrics/advanced` | `{ sopr, ... }` |
| Cost Basis | `/api/metrics/cost-basis` | `{ realized_price, short_term_holder_cost, long_term_holder_cost, ... }` |
| Binary CDD | `/api/metrics/binary-cdd` | `{ binary_cdd_30d, binary_cdd_60d, ... }` |
| Hash Ribbons | `/api/metrics/mining-pulse` | `{ hash_rate_ma_30d, hash_rate_ma_60d, miner_capitulation, ... }` |
| Wallet Waves | `/api/metrics/wallet-waves` | `{ cohorts: [...], ... }` |
| Exchange Netflow | `/api/metrics/exchange-netflow` | `{ inflow, outflow, netflow, ... }` |

### History Endpoints

Most metrics have `/history` variants:
- `/api/metrics/nupl` → current value
- `/api/metrics/nupl/history?days=365` → historical series

**Decision**: Use history endpoints for chart data, current endpoints for latest value display.

## 3. Plotly.js Best Practices

### CDN Integration

```html
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
```

**Decision**: Use specific version (2.27.0) for stability, not `latest`.

### Dark Theme Configuration

```javascript
const darkLayout = {
  paper_bgcolor: '#1a1a2e',
  plot_bgcolor: '#16213e',
  font: { color: '#e4e4e4' },
  xaxis: { gridcolor: '#374151', linecolor: '#374151' },
  yaxis: { gridcolor: '#374151', linecolor: '#374151' }
};
```

### Responsive Config

```javascript
const config = {
  responsive: true,
  displayModeBar: true,
  modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d']
};
```

## 4. Decisions Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Charting Library | Plotly.js 2.27.0 (CDN) | Matches CheckOnChain, no build needed |
| Theme | Dark (#1a1a2e background) | Visual consistency with reference |
| Data Source | Local API /history endpoints | Self-hosted, no external dependencies |
| Zone Coloring | Gradient fills per metric | Matches CheckOnChain UX |
| Price Overlay | Secondary y-axis (orange) | Standard practice for context |
| Shared Code | metrics-common.js | DRY principle, reusable fetch/render |

## 5. Alternatives Considered

| Alternative | Why Rejected |
|-------------|--------------|
| Chart.js | Less sophisticated than Plotly for financial data |
| D3.js | Too low-level, more code for same result |
| npm/bundler | Violates KISS, unnecessary for static pages |
| Light theme | Won't match CheckOnChain for visual comparison |
| External API (CoinGecko) | Violates privacy principles |
