# Implementation Plan: Metrics Dashboard Pages

**Branch**: `032-metrics-dashboard` | **Date**: 2025-12-19 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/032-metrics-dashboard/spec.md`

## Summary

Create dedicated Plotly.js chart pages for on-chain metrics (MVRV, NUPL, SOPR, Cost Basis, Hash Ribbons) that match CheckOnChain.com visual style for validation purposes. Pages consume existing FastAPI endpoints and render interactive charts.

## Technical Context

**Language/Version**: JavaScript (ES6+), HTML5, CSS3
**Primary Dependencies**: Plotly.js 2.x (CDN), FastAPI backend (existing)
**Storage**: N/A (frontend only, API provides data)
**Testing**: Manual visual validation + Playwright screenshot comparison
**Target Platform**: Modern browsers (Chrome, Firefox, Safari)
**Project Type**: Web frontend (static HTML pages)
**Performance Goals**: Chart load < 2s, responsive on mobile/desktop
**Constraints**: No build tools (vanilla JS), must match CheckOnChain visual style
**Scale/Scope**: 8 chart pages, 2 shared JS modules, 1 CSS file

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Code Quality & Simplicity | PASS | Vanilla JS, no framework, CDN Plotly only |
| II. Test-First Discipline | N/A | Frontend validated via visual comparison (spec-031) |
| III. User Experience Consistency | PASS | Dark theme, responsive, consistent with existing frontend |
| IV. Performance Standards | PASS | <2s load target, no heavy dependencies |
| V. Data Privacy & Security | PASS | All data from local API, no external calls |

**Gate Status: PASS** - No violations. Simple frontend pages consuming existing API.

## Project Structure

### Documentation (this feature)

```
specs/032-metrics-dashboard/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (API response schemas)
├── quickstart.md        # Phase 1 output
└── contracts/           # N/A (using existing API contracts)
```

### Source Code (repository root)

```
frontend/
├── metrics/             # NEW: Metric chart pages
│   ├── mvrv.html
│   ├── nupl.html
│   ├── sopr.html
│   ├── cost_basis.html
│   ├── hash_ribbons.html
│   ├── binary_cdd.html
│   ├── wallet_waves.html
│   └── exchange_netflow.html
├── js/
│   ├── metrics-common.js    # NEW: Shared fetch/render utilities
│   └── chart-themes.js      # NEW: Plotly theme configs
├── css/
│   └── metrics.css          # NEW: Metric page styling
└── [existing files...]
```

**Structure Decision**: Extend existing `frontend/` directory with new `metrics/` subdirectory for chart pages. Shared utilities in `js/` following existing patterns.

## Complexity Tracking

*No violations to justify - simple frontend addition.*

---

## Phase 0: Research Outcomes

See [research.md](research.md) for detailed findings.

**Key Decisions:**
1. Use Plotly.js CDN (no npm/bundler needed)
2. Match CheckOnChain dark theme for visual comparison
3. Fetch data from existing API endpoints with history support
4. Zone coloring configurable per metric

## Phase 1: Design Outputs

- **Data Model**: [data-model.md](data-model.md) - API response schemas used by frontend
- **Quickstart**: [quickstart.md](quickstart.md) - Development setup instructions
- **Contracts**: N/A - Using existing `/api/metrics/*` endpoints

## Next Steps

Run `/speckit.tasks` to generate implementation tasks after design review.
