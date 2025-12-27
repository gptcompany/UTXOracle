# Implementation Plan: ResearchBitcoin.net API Integration

**Branch**: `035-rbn-api-integration` | **Date**: 2025-12-26 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/035-rbn-api-integration/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Create a lightweight integration layer to fetch metrics from ResearchBitcoin.net (RBN) for validation, comparison, and gap-filling of UTXOracle's on-chain metrics. The integration provides cross-validation against RBN's 300+ metrics catalog with intelligent caching, rate limiting, and tolerance-based comparison reporting.

## Technical Context

**Language/Version**: Python 3.10+ (matches existing pyproject.toml requirement)
**Primary Dependencies**: httpx (async HTTP client), pandas (data manipulation), existing FastAPI backend
**Storage**: Parquet files in `cache/rbn/` for 24-hour caching; no new database tables
**Testing**: pytest with pytest-asyncio (existing stack)
**Target Platform**: Linux server (same as existing FastAPI deployment)
**Project Type**: Single project - integration module extends existing API
**Performance Goals**:
- Rate limit: max 1 request/second to RBN (per spec legal requirements)
- Cache TTL: 24 hours
- Comparison latency: <500ms for cached metrics
**Constraints**:
- No authenticated RBN API (public data only, no paid PRO metrics initially)
- R-CRAN/Shiny backend requires reverse-engineering endpoints
- RBN API: REST at `https://api.researchbitcoin.net/v1/{category}/{data_field}` (resolved in research.md)
**Scale/Scope**:
- Priority 1: 5 validation metrics (MVRV, SOPR, NUPL, Reserve Risk, Realized Cap)
- Priority 2: 5 gap-filling metrics (Thermocap, CVDD, S2F, Pi Cycle, 200W SMA)
- Total: ~10 metrics in initial scope

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Principle I: Code Quality & Simplicity ✅ PASS
| Requirement | Compliance |
|-------------|------------|
| KISS/YAGNI | ✅ Single-purpose fetcher and validator modules |
| Boring technology | ✅ httpx (standard async HTTP), pandas (existing), Parquet (existing pattern) |
| Single module purpose | ✅ `rbn_fetcher.py` = fetch, `rbn_validator.py` = compare |
| Minimize dependencies | ✅ httpx already in project deps; no new deps required |
| No premature abstraction | ✅ Direct fetch → cache → compare; no generic "external API framework" |

### Principle II: Test-First Discipline ✅ PASS
| Requirement | Compliance |
|-------------|------------|
| TDD cycle | ✅ Tests will use mock HTTP responses; no live RBN in CI |
| 80% coverage | ✅ Feasible: core logic is parseable without external deps |
| Integration tests | ✅ Required for: cache invalidation, comparison tolerance logic |

### Principle III: User Experience Consistency ✅ PASS
| Requirement | Compliance |
|-------------|------------|
| API Standards | ✅ New `/api/v1/validation/rbn/{metric_id}` follows existing patterns |
| JSON responses | ✅ Matches existing FastAPI response models |

### Principle IV: Performance Standards ✅ PASS
| Requirement | Compliance |
|-------------|------------|
| Resource limits | ✅ 1 req/sec rate limit; cached data <10MB per metric |
| Logging | ✅ Structured logging via existing structlog |

### Principle V: Data Privacy & Security ⚠️ REVIEW REQUIRED
| Requirement | Compliance |
|-------------|------------|
| Privacy-first | ⚠️ Fetches data FROM external source (RBN), but UTXOracle data stays local |
| No third-party transmission | ✅ We only pull public metrics; no UTXOracle data sent to RBN |
| Input validation | ✅ Validate metric IDs, date ranges before requests |
| Rate limiting | ✅ Built-in per legal requirements |

**Principle V Note**: This integration fetches FROM external source for validation but does NOT transmit any UTXOracle calculations or user data externally. The privacy-first principle is preserved.

## Project Structure

### Documentation (this feature)

```
specs/035-rbn-api-integration/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output: RBN API discovery results
├── data-model.md        # Phase 1 output: Pydantic models
├── quickstart.md        # Phase 1 output: Usage guide
├── contracts/           # Phase 1 output: OpenAPI fragment
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```
scripts/integrations/             # NEW directory for external integrations
├── __init__.py
├── rbn_fetcher.py               # Core RBN data fetching logic
└── rbn_validator.py             # Comparison/validation service

api/
├── main.py                      # Add validation router
└── models/
    └── validation_models.py     # NEW: RBNMetric, MetricComparison, etc.

tests/
├── test_rbn_integration.py      # Unit + integration tests
└── fixtures/
    └── rbn_mock_responses/      # Mock HTML/JSON from RBN

cache/rbn/                       # Runtime: cached Parquet files (gitignored)
```

**Structure Decision**: Extends existing project structure with new `scripts/integrations/` module for external data sources. This follows the pattern of `scripts/metrics/`, `scripts/derivatives/`, etc. API endpoints added to existing `api/main.py` router.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| External HTTP dependency | Validation requires external ground truth | No alternative - RBN is the comparison target |
| Parquet caching | Avoid repeated external requests | In-memory cache insufficient for 24hr TTL across restarts |

## Phase 0 Research Tasks

The following areas require investigation before Phase 1 design:

1. **RBN API Endpoint Discovery**: Reverse-engineer Shiny/R-CRAN data endpoints
2. **Data Format Analysis**: Determine response format (CSV, JSON, or HTML scraping)
3. **Rate Limit Verification**: Confirm acceptable request frequency
4. **Available Metrics Catalog**: Map RBN metric IDs to UTXOracle equivalents

## Phase 1 Design Artifacts (Generated)

- `research.md`: API discovery findings, endpoint mapping, tier limits
- `data-model.md`: Pydantic models (RBNConfig, RBNMetricInfo, MetricComparison, ValidationReport)
- `contracts/validation.yaml`: OpenAPI 3.0 specification for validation endpoints
- `quickstart.md`: Developer guide with CLI, API, and Python usage examples

## Constitution Check (Post-Design Re-evaluation)

*Re-evaluated after Phase 1 design completion.*

### Principle I: Code Quality & Simplicity ✅ PASS
- **Boring technology**: httpx is well-established async HTTP client, no custom protocols
- **Single purpose**: `rbn_fetcher.py` fetches, `rbn_validator.py` compares
- **No abstraction**: Direct REST API calls, no "external API framework"

### Principle II: Test-First Discipline ✅ PASS
- Mock responses in `tests/fixtures/rbn_mock_responses/` enable offline testing
- Integration tests for cache TTL and comparison tolerance logic
- No live RBN calls in CI (preserves quota)

### Principle III: User Experience Consistency ✅ PASS
- New endpoints follow existing `/api/v1/` patterns
- JSON responses match existing FastAPI models
- CLI follows existing `python -m scripts.*` pattern

### Principle IV: Performance Standards ✅ PASS
- 24-hour Parquet cache reduces API calls
- Weekly quota tracking prevents overages
- <500ms comparison latency for cached data

### Principle V: Data Privacy & Security ✅ PASS (Updated)
- **Data direction**: Inbound only (RBN → UTXOracle)
- **No outbound transmission**: UTXOracle calculations never sent externally
- **Token security**: Stored in `.env`, never logged
- **Input validation**: Pydantic models validate all parameters

**Post-Design Status**: All 5 principles PASS. No constitution violations detected.
