# Research: Validation Framework

## Overview

Research findings for completing the UTXOracle validation framework against CheckOnChain.com reference.

## Research Questions Resolved

### 1. How to capture screenshots for visual comparison?

**Decision**: Use Playwright MCP server

**Rationale**:
- Already configured in `.mcp.json`
- Provides `mcp__playwright__browser_navigate` and `mcp__playwright__browser_take_screenshot`
- Cross-browser support (Chromium, Firefox, WebKit)
- Headless mode for CI/CD

**Alternatives Considered**:
- Chrome DevTools MCP: More complex setup, less reliable for batch screenshots
- Puppeteer: Would require separate installation, not MCP-integrated
- Manual screenshots: Not automatable

### 2. How to extract data from CheckOnChain charts?

**Decision**: Parse Plotly.js JSON embedded in HTML

**Rationale**:
- CheckOnChain uses Plotly.js for all charts
- Data is embedded in `Plotly.newPlot()` calls within `<script>` tags
- Existing `checkonchain_fetcher.py` already implements this extraction
- Rate limiting (1 req/2s) and caching (1 hour) prevent abuse

**Implementation Details**:
```python
# Pattern: Plotly.newPlot("uuid", [{x: [...], y: [...]}], layout)
match = re.search(r'Plotly\.newPlot\s*\(\s*["\'][a-f0-9-]+["\']\s*,\s*\[', html)
```

### 3. What tolerance thresholds to use?

**Decision**: Per-metric tolerances based on data characteristics

| Metric | Tolerance | Rationale |
|--------|-----------|-----------|
| mvrv_z | ±2% | Relatively stable, low volatility |
| nupl | ±2% | Similar to MVRV |
| sopr | ±1% | More sensitive, tighter tolerance |
| sth_sopr | ±2% | Cohort-specific, slightly more variance |
| lth_sopr | ±2% | Cohort-specific, slightly more variance |
| cdd | ±5% | High variance metric |
| binary_cdd | 0% | Boolean - must match exactly |
| cost_basis | ±2% | Price-based, relatively stable |
| hash_ribbons | ±3% | Mining metrics have natural variance |

**Source**: Defined in `validator.py` TOLERANCES dict.

### 4. How to integrate with spec-032 frontend pages?

**Decision**: Direct URL mapping

| Metric | Our Page | CheckOnChain Reference |
|--------|----------|----------------------|
| MVRV | `http://localhost:8080/metrics/mvrv.html` | `https://charts.checkonchain.com/btconchain/unrealised/mvrv_all/mvrv_all_light.html` |
| NUPL | `http://localhost:8080/metrics/nupl.html` | `https://charts.checkonchain.com/btconchain/unrealised/nupl/nupl_light.html` |
| SOPR | `http://localhost:8080/metrics/sopr.html` | `https://charts.checkonchain.com/btconchain/realised/sopr/sopr_light.html` |
| Cost Basis | `http://localhost:8080/metrics/cost_basis.html` | `https://charts.checkonchain.com/btconchain/realised/realised_price/realised_price_light.html` |
| Hash Ribbons | `http://localhost:8080/metrics/hash_ribbons.html` | `https://charts.checkonchain.com/btconchain/mining/hashribbons/hashribbons_light.html` |
| Binary CDD | `http://localhost:8080/metrics/binary_cdd.html` | `https://charts.checkonchain.com/btconchain/lifespan/cdd_all/cdd_all_light.html` |

**Note**: Wallet Waves and Exchange Netflow don't have direct CheckOnChain equivalents.

### 5. How to structure visual validation workflow?

**Decision**: Three-step process with MCP tools

```
1. Navigate to our page → Take screenshot → Save to screenshots/ours/
2. Navigate to CheckOnChain → Take screenshot → Save to screenshots/reference/
3. Compare screenshots → Generate deviation report
```

**MCP Tool Sequence**:
```python
# Step 1: Our chart
mcp__playwright__browser_navigate(url="http://localhost:8080/metrics/mvrv.html")
mcp__playwright__browser_take_screenshot(path="screenshots/ours/mvrv.png")

# Step 2: Reference
mcp__playwright__browser_navigate(url="https://charts.checkonchain.com/...")
mcp__playwright__browser_take_screenshot(path="screenshots/reference/mvrv.png")
```

### 6. What tests are needed for the framework?

**Decision**: Unit tests for each component + integration test

| Test File | Coverage |
|-----------|----------|
| test_validator.py | MetricValidator class, compare(), tolerance logic |
| test_fetcher.py | CheckOnChainFetcher, Plotly extraction, caching |
| test_comparison.py | ComparisonEngine, report generation |

**Test Fixtures**:
- Mock HTTP responses for CheckOnChain pages
- Sample Plotly.js data structures
- Pre-computed baseline files

## Technical Decisions Summary

1. **Screenshot Tool**: Playwright MCP (already configured)
2. **Data Extraction**: Plotly.js JSON parsing (existing implementation)
3. **Tolerances**: Per-metric, 1-5% range (defined in code)
4. **Frontend Integration**: Direct URL mapping to spec-032 pages
5. **Visual Workflow**: Navigate → Capture → Compare → Report
6. **Testing**: pytest with mocked HTTP responses

## Dependencies

- `httpx`: Already in use for HTTP requests
- `playwright`: Available via MCP server
- `pytest`: Standard test framework
- `pytest-httpx`: For mocking HTTP responses in tests

## Implementation Priority

1. **P0 - Critical**: Populate baselines (needed for any validation)
2. **P1 - High**: visual_validator.py (key missing component)
3. **P2 - Medium**: Tests (validation of validation framework)
4. **P3 - Low**: CI/CD GitHub Action (nice to have)
