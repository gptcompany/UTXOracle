# spec-046: Calculator Surface Productization

> **Status**: PARTIALLY IMPLEMENTED
> **Priority**: HIGH
> **Effort**: Large
> **Created**: 2026-04-01
> **Wave 1 Implemented**: 2026-04-01
> **Wave 2 Decision Frozen**: 2026-04-02
> **Selective Wave 2 Implemented**: 2026-04-02

## Problem Statement

`UTXOracle` already contains substantial analytical logic in `scripts/metrics`, but many corresponding API routes still return `501 Not Implemented`.

Current gaps:

1. calculator-backed routes exist, but are not consumable through the API
2. high-value feature families such as NUPL and cost basis are still trapped behind research-only API paths, while reserve-risk is both analytically incomplete and a duplication-risk case against `BRK`
3. history-dependent surfaces still lack persistent snapshot materialization even after Wave 1 route promotion
4. roadmap work cannot prioritize feature promotion without a wave-based plan

This spec productizes the most valuable calculator-backed surfaces in controlled waves. Wave 1 is now live; later waves and persistent history materialization remain open.

## Goals

1. convert selected `calculator only` routes from `501` to supported API surfaces
2. introduce history/snapshot materialization where required
3. define priority waves instead of attempting all calculators at once
4. add tests and empty/stale semantics for promoted surfaces

## Non-Goals

- promoting every `calculator only` route in one pass
- solving entity attribution in full
- exposing unfinished metrics with placeholder math as production-ready

## Dependencies

- [specs/017-utxo-lifecycle-engine/spec.md](/media/sam/1TB/UTXOracle/specs/017-utxo-lifecycle-engine/spec.md)
- [specs/023-cost-basis-cohorts/spec.md](/media/sam/1TB/UTXOracle/specs/023-cost-basis-cohorts/spec.md)
- [specs/025-wallet-waves/spec.md](/media/sam/1TB/UTXOracle/specs/025-wallet-waves/spec.md)
- [specs/039-address-balance-cohorts/spec.md](/media/sam/1TB/UTXOracle/specs/039-address-balance-cohorts/spec.md)
- [specs/044-feature-service-contract-registry/spec.md](/media/sam/1TB/UTXOracle/specs/044-feature-service-contract-registry/spec.md)
- [specs/045-feature-dependency-provenance-manifest/spec.md](/media/sam/1TB/UTXOracle/specs/045-feature-dependency-provenance-manifest/spec.md)

## Prioritized Waves

### Wave 1: Balance and Holder Structure

These are the highest-value first promotions because they support institutional-vs-retail interpretation and are already backed by clear DuckDB calculators:

- `/api/metrics/address-cohorts`
- `/api/metrics/wallet-waves`
- `/api/metrics/absorption-rates`

### Wave 2: Macro Holder Stress and Conviction

- `/api/metrics/reserve-risk`
- `/api/metrics/nupl`
- `/api/metrics/cost-basis`

Wave 2 audit result frozen on 2026-04-02:

- `/api/metrics/reserve-risk` stays out of the next promotion slice because the calculator still contains placeholder/default internals and the metric later becomes a `BRK`-first source-of-truth case rather than a default local productization target
- `/api/metrics/nupl` is shortlisted for the next selective promotion slice, with an explicit caveat that `pct_supply_in_profit` is currently an estimate
- `/api/metrics/cost-basis` is shortlisted for the next selective promotion slice as the strongest calculator-backed candidate

Selective Wave 2 implementation result on 2026-04-02:

- `/api/metrics/nupl` is now wired and returns a live DuckDB-backed response
- `/api/metrics/cost-basis` is now wired and returns a live DuckDB-backed response
- `/api/metrics/reserve-risk` remains intentionally unpromoted and should not be treated as the default next local productization slice
- any future admission of `nupl` or `cost-basis` beyond `tier_3_research` is now delegated to `spec-049`

### Wave 3: Broader Research Metrics

- `/api/metrics/revived-supply`
- `/api/metrics/cdd-vdd`
- `/api/metrics/urpd`
- `/api/metrics/supply-profit-loss`
- `/api/metrics/sell-side-risk`
- `/api/metrics/cointime*`
- `/api/metrics/wasserstein*`

## Design

### 1. Promotion Rule

A route may leave `501` only when all of the following are true:

1. the calculator is wired to the API
2. backend dependency is declared
3. empty/stale semantics are defined
4. tests exist for healthy and degraded cases

### 2. History Materialization

Any route that depends on historical snapshots MUST define:

- the persistence table
- the writer job or schedule
- baseline backfill requirements
- empty-state behavior before enough history exists

This is mandatory for:

- wallet waves history
- absorption rates
- any future time-series endpoint derived from daily snapshots

### 3. Promotion Output Contract

Every promoted route MUST declare:

- current backend
- freshness target
- confidence or data quality notes where applicable
- expected 404/503/empty behavior

### 4. API Policy

Promoted routes MUST remain under existing paths unless a breaking move is explicitly approved by the contract registry.

### 5. Wave Completion

A wave is complete only when:

- routes no longer return `501`
- route tests pass
- contract registry is updated
- provenance manifest is updated

## Functional Requirements

### FR1: Wave-Based Promotion

The implementation MUST promote calculator-backed surfaces in explicit waves.

### FR2: Wave 1 Delivery

Wave 1 MUST be the first implementation slice.

### FR3: History Support

Routes requiring historical baselines MUST define persistent materialization before being treated as supported.

### FR4: No Placeholder Promotion

A calculator-backed route MUST NOT be promoted if the API output still depends on mocked or hardcoded analytical inputs.

### FR5: Contract Updates

Every promoted route MUST update spec-044 and spec-045 artifacts.

### FR6: Test Coverage

Every promoted route family MUST have tests for:

- healthy path
- missing backend/data
- empty state
- stale or insufficient-history behavior where applicable

### FR7: Selective Wave 2 Promotion

Wave 2 does not need to ship as an all-or-nothing bundle. Individual routes may advance to the next milestone while others remain held with explicit blockers.

## Success Criteria

1. Wave 1 routes stop returning `501`
2. Wave 1 routes have explicit backend and failure semantics
3. history-dependent routes have snapshot materialization defined
4. roadmap work can refer to promotion waves instead of an undifferentiated `calculator only` bucket
5. Wave 2 has an explicit freeze decision: `nupl` and `cost-basis` are the next candidates, while `reserve-risk` remains blocked
6. selective Wave 2 routes (`nupl`, `cost-basis`) leave the `501` bucket without forcing `reserve-risk` through premature promotion
7. overlapping metrics may be de-scoped from local productization entirely if a later source-of-truth manifest freezes `BRK` as the preferred shared production source
