# Implementation Plan: Wasserstein Distance Calculator

**Branch**: `010-wasserstein-distance` | **Date**: 2025-12-04 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/010-wasserstein-distance/spec.md`

## Summary

Implement a Wasserstein Distance Calculator (Earth Mover's Distance) to detect distribution shifts in UTXO value patterns. The module will compute 1D EMD using CDF integration, provide rolling window analysis for regime detection, and integrate as the 8th component in the Enhanced Monte Carlo Fusion from spec-009.

**Primary Value**: +5% accuracy improvement in regime shift detection (per Horvath et al. 2024)

## Technical Context

**Language/Version**: Python 3.11+ (matches existing codebase)
**Primary Dependencies**: None (pure Python, no numpy/scipy required)
**Storage**: DuckDB (extend existing `metrics` table)
**Testing**: pytest with fixtures from `tests/fixtures/`
**Target Platform**: Linux server (same as daily_analysis.py)
**Project Type**: Single project (metrics module extension)
**Performance Goals**: <50ms per Wasserstein calculation for 1000-sample distributions
**Constraints**: Pure Python (no scipy.stats), backward compatible with spec-009
**Scale/Scope**: Batch processing, 1000-10000 samples per window typical

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Principle I: Code Quality & Simplicity ✅ PASS

| Requirement | Status | Evidence |
|-------------|--------|----------|
| KISS: boring technology | ✅ | Pure Python, no new dependencies |
| YAGNI: no generic solutions | ✅ | Single-purpose: 1D Wasserstein only |
| Single purpose per module | ✅ | `wasserstein.py` does one thing |
| Minimize dependencies | ✅ | Zero external dependencies |
| Readable code | ✅ | CDF integration is standard algorithm |

### Principle II: Test-First Discipline ✅ PASS

| Requirement | Status | Evidence |
|-------------|--------|----------|
| TDD RED-GREEN-REFACTOR | ✅ | Tests written first in `tests/test_wasserstein.py` |
| 80% coverage minimum | ✅ | Target 85% per spec |
| Integration tests | ✅ | Test integration with enhanced_fusion |

### Principle III: User Experience Consistency ✅ PASS

| Requirement | Status | Evidence |
|-------------|--------|----------|
| CLI standards | N/A | No CLI changes |
| API standards | ✅ | New endpoint follows existing patterns |
| Output format | ✅ | Dataclass matches spec-009 patterns |

### Principle IV: Performance Standards ✅ PASS

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Batch processing speed | ✅ | <50ms target per calculation |
| Memory limits | ✅ | O(n) space, within <500MB RAM |
| Logging | ✅ | Follow existing patterns |

### Principle V: Data Privacy & Security ✅ PASS

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Local-first processing | ✅ | All computation local |
| No external APIs | ✅ | Pure Python, no network calls |
| Input validation | ✅ | Pydantic models for validation |

**Constitution Gate: PASSED** - No violations, no complexity tracking needed.

## Project Structure

### Documentation (this feature)

```
specs/010-wasserstein-distance/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── wasserstein_api.yaml
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```
scripts/
├── metrics/
│   ├── __init__.py              # Update exports
│   ├── wasserstein.py           # NEW: Core Wasserstein module
│   ├── monte_carlo_fusion.py    # MODIFY: Add 8th component
│   └── ...existing modules...
├── models/
│   └── metrics_models.py        # MODIFY: Add WassersteinResult
└── daily_analysis.py            # MODIFY: Add Wasserstein to pipeline

api/
└── main.py                      # MODIFY: Add /api/metrics/wasserstein

tests/
├── test_wasserstein.py          # NEW: Unit tests
└── integration/
    └── test_wasserstein_integration.py  # NEW: Integration tests
```

**Structure Decision**: Extend existing `scripts/metrics/` module structure (matches spec-007, spec-009 patterns).

## Complexity Tracking

*No violations - table not required.*

---

## Phase 0: Research

See [research.md](./research.md) for detailed findings.

**Research Topics**:
1. Optimal 1D Wasserstein algorithm for discrete distributions
2. Rolling window strategies for regime detection
3. Integration patterns with existing Monte Carlo fusion

## Phase 1: Design

See:
- [data-model.md](./data-model.md) - Entity definitions
- [contracts/](./contracts/) - API contracts
- [quickstart.md](./quickstart.md) - Usage examples
