# Research: ResearchBitcoin.net API Integration

**Phase 0 Research Output** | **Date**: 2025-12-26 | **Spec**: [spec.md](./spec.md)

## Executive Summary

ResearchBitcoin.net (RBN) provides a well-documented REST API with 300+ on-chain metrics. The API uses token-based authentication with a generous free tier (100 queries/week, 1 year history). This research resolves all NEEDS CLARIFICATION items from the Technical Context.

## Research Findings

### 1. RBN API Endpoint Discovery

**Decision**: Use official REST API at `https://api.researchbitcoin.net/v1`

**Rationale**:
- RBN provides a documented, versioned API (v1) with OpenAPI/Swagger specification
- No reverse-engineering required - endpoints are publicly documented
- The original spec mentioned R-CRAN/Shiny, but RBN uses **Dash (Plotly)** for frontend and REST API for data

**Alternatives Considered**:
- Web scraping: Rejected - unnecessary complexity when API exists
- Dash callback interception: Rejected - API is simpler and officially supported
- Direct database access: Not available

**API Base URL**: `https://api.researchbitcoin.net/v1`

**Endpoint Pattern**: `/{category}/{data_field}`

| Category | Tier | Example Endpoints |
|----------|------|-------------------|
| `address_statistics` | 0 | active_addresses_balance_sum, new_addresses_count |
| `cointime_statistics` | 0 | active_cap, liveliness, supply_active |
| `market_value_to_realized_value` | 0 | mvrv, mvrv_z, mvrv_lth |
| `profit_loss` | 0 | nupl, sopr, realized_profit |
| `supply_distribution` | 0 | supply_lth, supply_sth, supply_total |
| `price_models` | 0 | price_power_law_qr, price_log_alldata_ols |
| `hodl_by_age` | 2 | hodl_age_supply, rhodl_ratio |
| `utxo_distributions` | 2 | urpd_log_supply |

### 2. Data Format Analysis

**Decision**: Use JSON format for API responses

**Rationale**:
- API supports both JSON and CSV (`output_format` parameter)
- JSON integrates directly with Python dict/Pydantic models
- CSV would require extra parsing step

**Response Schema** (from Swagger):
```json
{
  "status": "success",
  "message": "Data retrieved successfully",
  "data": {
    "dates": ["2024-01-01", "2024-01-02", ...],
    "values": [1.23, 1.45, ...]
  },
  "output_format": "json",
  "timestamp": "2025-12-26T10:00:00Z"
}
```

**Error Schema**:
```json
{
  "status": "error",
  "error": "Invalid token or insufficient quota",
  "timestamp": "2025-12-26T10:00:00Z",
  "details": {"remaining_quota": 0}
}
```

**Date Parameter Format**: `YYYY-MM-DD` (e.g., `2024-12-01`)

### 3. Rate Limit Verification

**Decision**: Implement 100 queries/week limit with local tracking

**Rationale**:
- Free tier (Tier 0) allows 100 queries per week
- Rate limit resets weekly (not per-second as originally assumed in spec)
- No per-second rate limit documented - the 1 req/sec in spec was overly conservative

**Tier Limits**:
| Tier | Weekly Queries | History | Metrics Access |
|------|----------------|---------|----------------|
| 0 (Free) | 100 | 1 year | Most metrics |
| 1 | 300 | Full | Tier 0 + Tier 1 |
| 2 | 10,000 | Full | All metrics |

**Implementation Strategy**:
- Track queries locally in SQLite or JSON file
- Cache responses for 24 hours to minimize API calls
- Batch validation requests (e.g., weekly batch job)

### 4. Available Metrics Catalog

**Decision**: Prioritize Tier 0 metrics for free validation

**UTXOracle-to-RBN Mapping (Confirmed)**:

| UTXOracle Spec | RBN Endpoint | RBN Category | Tier |
|----------------|--------------|--------------|------|
| spec-007 (MVRV) | `mvrv`, `mvrv_z` | `/market_value_to_realized_value/` | 0 |
| spec-007 (MVRV LTH/STH) | `mvrv_lth`, `mvrv_sth`, `mvrv_z_lth`, `mvrv_z_sth` | `/market_value_to_realized_value/` | 0 |
| spec-016 (SOPR) | `sopr`, `sopr_lth`, `sopr_sth` | `/spent_output_profit_ratio/` | 0 |
| spec-007 (NUPL) | `net_unrealized_profit_loss`, `_lth`, `_sth` | `/net_unrealized_profit_loss/` | 0 |
| spec-007 (Realized Cap) | `realized_cap`, `_lth`, `_sth` | `/realizedcap/` | 0 |
| spec-034 (Power Law) | `price_power_law_qr`, `price_power_law_ols` | `/price_models/` | 0 |
| spec-018 (Cointime) | `liveliness`, `cointime_price`, `active_cap` | `/cointime_statistics/` | 0 |

**Gap-Filling Metrics Available (Priority 2)**:

| Metric | RBN Endpoint | RBN Category | Tier |
|--------|--------------|--------------|------|
| Thermocap | `thermo_cap` | `/cointime_statistics/` | 0 |
| S2F (nominal) | `stocktoflow_nominal` | `/cointime_statistics/` | 0 |
| S2F (cointime-adjusted) | `stocktoflow_cointime_adj` | `/cointime_statistics/` | 0 |
| Active MVRV | `active_mvrv` | `/cointime_statistics/` | 0 |
| NVT (cointime) | `cointime_nvt` | `/cointime_statistics/` | 0 |
| RHODL Ratio | `rhodl_ratio` | `/hodl_by_age/` | **2** |
| URPD distributions | Multiple | `/utxo_distributions/` | **2** |

**Not Available on RBN**:
- Pi Cycle Top: Compute locally from price + MA crossovers
- 200-week SMA Heatmap: Compute locally from price

### 5. Authentication Method

**Decision**: Token-based authentication via query parameter

**Token Format**: UUID (`xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`)

**Token Acquisition**:
1. Register at `/token` page (free for Tier 0)
2. Token stored locally in `.env` file or config
3. Include in all requests: `?token={API_TOKEN}`

**Token Response** (`/info_user/` endpoint):
```json
{
  "email": "user@example.com",
  "tier": 0,
  "quota_remaining": 95,
  "quota_reset": "2025-01-02T00:00:00Z"
}
```

## Updated Technical Context

Based on research, the Technical Context is updated:

| Item | Original | Updated |
|------|----------|---------|
| API Structure | NEEDS CLARIFICATION | REST API at `/v1/{category}/{field}` |
| Authentication | Unknown | Token via query parameter |
| Rate Limit | 1 req/sec | 100 queries/week (Tier 0) |
| Data Format | Unknown | JSON (preferred) or CSV |
| Framework | R-CRAN/Shiny | Dash (frontend) + REST API |

## Implementation Implications

### Caching Strategy (Updated)
- 24-hour TTL remains appropriate
- Weekly batch validation recommended to stay within quota
- Local quota tracking prevents overages

### Error Handling
- HTTP 401: Invalid/expired token
- HTTP 422: Invalid parameters (date format, unknown field)
- HTTP 429: Quota exceeded (unlikely with local tracking)

### Dependency Changes
- `httpx` confirmed (async HTTP client)
- No Shiny-specific dependencies needed
- Token management requires secure storage

## Open Questions

1. **Token acquisition process**: Manual registration required - no automated signup
2. **Tier 2 metrics**: HODL waves and URPD require paid tier for full history
3. **Reserve Risk exact endpoint**: Need live API test to confirm path

## Sources

- [Bitcoin Lab API Home](https://api.researchbitcoin.net/)
- [API Data Fields (deprecated docs)](https://researchbitcoin.net/api-data-fields/)
- [API Tier Information](https://api.researchbitcoin.net/tier)
- [Swagger Specification](https://api.researchbitcoin.net/v1/swagger.json)
