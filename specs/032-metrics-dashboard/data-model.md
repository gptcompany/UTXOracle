# Data Model: Metrics Dashboard Pages

## Overview

Frontend pages consume existing FastAPI endpoints. This document captures the response schemas for chart rendering.

## API Response Schemas

### 1. MVRV-Z Score

**Endpoint**: `GET /api/metrics/advanced`

```typescript
interface AdvancedMetricsResponse {
  mvrv_z: number;          // MVRV Z-Score value
  sopr: number;            // SOPR value
  nupl: number;            // NUPL value
  sthrp: number;           // Short-term holder realized price
  lthrp: number;           // Long-term holder realized price
  realized_price: number;  // Overall realized price
  market_price: number;    // Current market price
  timestamp: string;       // ISO 8601 date
}
```

**Chart Data**: For historical chart, call `/api/metrics/wasserstein/history?days=365`

### 2. NUPL

**Endpoint**: `GET /api/metrics/nupl`

```typescript
interface NUPLResponse {
  nupl: number;            // Net Unrealized P/L (-1 to 1)
  unrealized_profit: number;
  unrealized_loss: number;
  market_cap: number;
  realized_cap: number;
  date: string;            // ISO 8601 date
}
```

**History**: `GET /api/metrics/nupl/history?days=365` (if available)

### 3. SOPR

**Endpoint**: `GET /api/metrics/advanced`

```typescript
// Uses AdvancedMetricsResponse.sopr
// SOPR > 1: profit, SOPR < 1: loss, SOPR = 1: break-even
```

### 4. Cost Basis

**Endpoint**: `GET /api/metrics/cost-basis`

```typescript
interface CostBasisResponse {
  realized_price: number;           // Overall realized price
  short_term_holder_cost: number;   // STH cost basis
  long_term_holder_cost: number;    // LTH cost basis
  market_price: number;             // Current price
  mvrv_ratio: number;               // Market/Realized ratio
  date: string;
}
```

### 5. Binary CDD

**Endpoint**: `GET /api/metrics/binary-cdd`

```typescript
interface BinaryCDDResponse {
  binary_cdd_30d: boolean;  // 30-day signal
  binary_cdd_60d: boolean;  // 60-day signal
  cdd_raw: number;          // Raw CDD value
  cdd_30d_ma: number;       // 30-day moving average
  cdd_60d_ma: number;       // 60-day moving average
  date: string;
}
```

### 6. Hash Ribbons (Mining Pulse)

**Endpoint**: `GET /api/metrics/mining-pulse`

```typescript
interface MiningPulseResponse {
  hash_rate_ma_30d: number;     // 30-day hash rate MA
  hash_rate_ma_60d: number;     // 60-day hash rate MA
  miner_capitulation: boolean;  // Capitulation signal
  hash_ribbon_buy: boolean;     // Buy signal
  difficulty_ribbon: number;    // Difficulty ribbon
  date: string;
}
```

### 7. Wallet Waves

**Endpoint**: `GET /api/metrics/wallet-waves`

```typescript
interface WalletWavesResponse {
  cohorts: WalletCohort[];
  total_supply: number;
  date: string;
}

interface WalletCohort {
  age_range: string;    // e.g., "1d-1w", "1w-1m", "1m-3m"
  supply: number;       // BTC in cohort
  percentage: number;   // % of total supply
}
```

### 8. Exchange Netflow

**Endpoint**: `GET /api/metrics/exchange-netflow`

```typescript
interface ExchangeNetflowResponse {
  inflow: number;       // BTC flowing into exchanges
  outflow: number;      // BTC flowing out of exchanges
  netflow: number;      // inflow - outflow
  exchange_balance: number;
  date: string;
}
```

## Chart Data Transformations

### Plotly Trace Format

Each API response must be transformed into Plotly trace format:

```javascript
// Transform API response to Plotly trace
function apiToTrace(data, config) {
  return {
    x: data.map(d => d.date),
    y: data.map(d => d[config.valueKey]),
    type: 'scatter',
    mode: 'lines',
    name: config.name,
    fill: config.fill || 'none',
    fillcolor: config.fillcolor,
    line: { color: config.lineColor, width: 2 }
  };
}
```

### Zone Boundaries

| Metric | Zones | Colors |
|--------|-------|--------|
| MVRV-Z | [0, 3, 7] | green, gray, yellow, red |
| NUPL | [0, 0.25, 0.5, 0.75] | red, orange, yellow, lightgreen, green |
| SOPR | [1] | red, green |

## Data Flow

```
[FastAPI Backend] → [/api/metrics/*] → [JavaScript fetch()] → [Transform] → [Plotly.newPlot()]
```

## Error Handling

Frontend should handle:
- API unavailable (show "Loading..." or error message)
- Empty data (show "No data available")
- Invalid values (filter out null/undefined before plotting)
