# spec-031: Validation Framework

## Overview

Professional validation framework to verify UTXOracle metric implementations against CheckOnChain.com reference.

## Reference Source

**Primary**: CheckOnChain.com (https://checkonchain.com)
- Covers: MVRV, NUPL, SOPR, CDD, Cost Basis, Wallet Waves, Exchange Flows
- Technology: Plotly.js charts
- Access: Public (free tier)

## Validation Layers

### Layer 1: Numerical Validation (Immediate)
Compare API response values with CheckOnChain data points.

| Metric | CheckOnChain Equivalent | Tolerance |
|--------|------------------------|-----------|
| MVRV-Z Score | MVRV Z-Score | ±2% |
| NUPL | Net Unrealized P/L | ±2% |
| SOPR | Spent Output Profit Ratio | ±1% |
| STH/LTH SOPR | STH-SOPR, LTH-SOPR | ±2% |
| CDD | Coin Days Destroyed | ±5% |
| Binary CDD | CDD Heatmap (derived) | Boolean match |
| Cost Basis | Realized Price | ±2% |
| Hash Ribbons | Mining: Hash Ribbons | ±3% |

### Layer 2: Visual Validation (After Frontend)
Screenshot comparison using Playwright/Chrome DevTools.

**Tools Available**:
- `mcp__playwright__browser_navigate`
- `mcp__playwright__browser_take_screenshot`
- `mcp__chrome-devtools__take_screenshot`
- `mcp__chrome-devtools__navigate_page`

**Workflow**:
1. Navigate to our chart page
2. Take screenshot
3. Navigate to CheckOnChain equivalent
4. Take screenshot
5. Compare trend shape, zones, value alignment
6. Generate deviation report

### Layer 3: Signal Validation
Verify buy/sell signals match historical events.

| Event | Date | Expected Signal |
|-------|------|-----------------|
| COVID Crash | 2020-03-12 | Capitulation |
| 2021 ATH | 2021-11-10 | Euphoria |
| 2022 Bear Bottom | 2022-11-21 | Capitulation |
| 2024 Halving | 2024-04-20 | Recovery |

## Implementation Plan

### Phase 0: Infrastructure (Day 1)
- [ ] Create validation/ directory structure
- [ ] Setup MCP config for visual tools
- [ ] Create reference data baseline files

### Phase 1: Numerical Validation (Days 2-4)
- [ ] Build validation framework (Python)
- [ ] Implement CheckOnChain scraper (respectful rate limiting)
- [ ] Create comparison engine
- [ ] Generate first validation report

### Phase 2: Frontend Charts (Days 5-10)
- [ ] MVRV page with Plotly.js
- [ ] NUPL page with zone coloring
- [ ] SOPR page with STH/LTH variants
- [ ] Mining Economics page
- [ ] Cost Basis page

### Phase 3: Visual Validation (Days 11-14)
- [ ] Configure alpha-visual subagent
- [ ] Implement screenshot comparison
- [ ] Create visual deviation reports
- [ ] Iterate until charts match

### Phase 4: CI/CD (Days 15-17)
- [ ] GitHub Action for nightly validation
- [ ] Slack/Discord alerts on deviation
- [ ] Automated regression detection

## Success Criteria

| Criterion | Target |
|-----------|--------|
| Numerical deviation | < 5% for all metrics |
| Visual trend match | 95% correlation |
| Signal accuracy | 100% on historical events |
| Regression rate | 0% after baseline |

## Directory Structure

```
validation/
├── spec.md                      # This file
├── framework/
│   ├── __init__.py
│   ├── validator.py             # Core validation logic
│   ├── checkonchain_fetcher.py  # Reference data fetcher
│   ├── comparison_engine.py     # Compare and report
│   └── visual_validator.py      # Screenshot comparison
├── baselines/
│   ├── mvrv_baseline.json
│   ├── nupl_baseline.json
│   └── ...
├── reports/
│   ├── YYYY-MM-DD_validation.md
│   └── ...
├── screenshots/
│   ├── ours/
│   └── reference/
└── tests/
    └── test_validation.py
```

## MCP Configuration

Add to `.mcp.json`:
```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest"]
    },
    "chrome-devtools": {
      "command": "npx",
      "args": ["chrome-devtools-mcp@latest"]
    }
  }
}
```
