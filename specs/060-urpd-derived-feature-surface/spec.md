# spec-060: URPD-Derived Feature Surface

> **Status**: COMPLETE
> **Priority**: HIGH
> **Effort**: Small
> **Created**: 2026-04-17

## Problem Statement

`UTXOracle` already has local `URPD` calculation logic and `BRK` exposes a richer `cost-basis` distribution surface, but neither path was frozen into a small, serving-grade, backtest-friendly feature surface.

Current gaps before this slice:

1. raw `URPD` remained a research-only calculator surface
2. the repo lacked a materialized historical table for distribution-derived scalar features
3. there was no admitted API contract for `URPD`-like intensity and concentration signals
4. backtest work would otherwise be forced to consume a histogram rather than stable scalar fields

The first useful step is not to expose raw histogram data. It is to freeze a narrow set of scalar features derived from the current cost-basis distribution.

## Goals

1. define a small canonical `URPD-derived` feature set
2. materialize that feature set into QuestDB as a daily historical surface
3. expose a stable latest-read API route for operators and downstream consumers
4. keep the contract small enough to be backtestable without carrying the full histogram
5. leave full backtest loader integration as an explicit next step instead of implicitly broadening this slice

## Non-Goals

- mirroring the full `BRK` cost-basis distribution into `UTXOracle`
- exposing raw `URPD` histogram buckets as a promoted serving-grade route
- freezing full entity/address clustering semantics in this spec
- completing the full backtest engine refactor in the same slice

## Dependencies

- [specs/023-cost-basis-cohorts/spec.md](/media/sam/1TB/UTXOracle/specs/023-cost-basis-cohorts/spec.md)
- [specs/046-calculator-surface-productization/spec.md](/media/sam/1TB/UTXOracle/specs/046-calculator-surface-productization/spec.md)
- [specs/052-btc-consumer-bundles-and-signal-snapshots/spec.md](/media/sam/1TB/UTXOracle/specs/052-btc-consumer-bundles-and-signal-snapshots/spec.md)
- [specs/054-production-boundary-and-surface-tiering/spec.md](/media/sam/1TB/UTXOracle/specs/054-production-boundary-and-surface-tiering/spec.md)

Primary references:

- [scripts/metrics/urpd.py](/media/sam/1TB/UTXOracle/scripts/metrics/urpd.py)
- [scripts/metrics/cost_basis.py](/media/sam/1TB/UTXOracle/scripts/metrics/cost_basis.py)
- [scripts/metrics/urpd_features.py](/media/sam/1TB/UTXOracle/scripts/metrics/urpd_features.py)
- [api/routes/questdb.py](/media/sam/1TB/UTXOracle/api/routes/questdb.py)
- [api/questdb_repository.py](/media/sam/1TB/UTXOracle/api/questdb_repository.py)
- [scripts/metrics/materialize_wave1.py](/media/sam/1TB/UTXOracle/scripts/metrics/materialize_wave1.py)
- [/media/sam/1TB/brk/packages/brk_client/DOCS.md](/media/sam/1TB/brk/packages/brk_client/DOCS.md)

## Current Baseline

The repo now has these relevant building blocks:

- local `URPD` calculation and tests
- local `cost_basis` calculator and QuestDB materialization path
- existing daily materialization job for holder/cohort metrics
- an admitted QuestDB route family under `:8011 /api/metrics/*`

Important baseline decisions already frozen before this spec:

- `UTXOracle` should not promote raw research histograms as a first serving-grade contract
- `cost_basis` remains locally owned unless exact upstream equivalence with `BRK` is explicitly verified and frozen
- `BRK` may remain the richer upstream source for future comparison or replacement work, but that migration is out of scope here

## Design

### 1. Canonical Feature Set

This spec freezes exactly five scalar fields derived from the current cost-basis distribution:

- `supply_below_price_pct`
- `supply_above_price_pct`
- `top_bucket_concentration`
- `dominant_bucket_distance_pct`
- `distribution_entropy`

Supporting metadata:

- `timestamp`
- `block_height`
- `current_price_usd`
- `bucket_size_usd`
- `total_supply_btc`
- `confidence`

This is intentionally a compressed feature surface, not a histogram transport.

Field notes:

- `confidence` is inherited from the local derived-feature calculation path and is meant as a coarse data-availability / calculation-health signal, not as a market conviction score
- `bucket_size_usd` is an explicit calculation parameter and MUST be stored with each row so the historical series remains interpretable if the configured bucket size changes later

### 2. Storage Contract

The canonical persistence table is:

- `urpd_features_daily`

Required columns:

- `ts`
- `block_height`
- `current_price_usd`
- `bucket_size_usd`
- `total_supply_btc`
- `supply_below_price_pct`
- `supply_above_price_pct`
- `top_bucket_concentration`
- `dominant_bucket_distance_pct`
- `distribution_entropy`
- `confidence`
- `created_at`

Cadence:

- daily or slower batch materialization is acceptable for the first slice
- this surface does not require intraday semantics in this spec

Idempotence rule:

- re-materialization for the same effective snapshot date MAY overwrite the previously stored row
- this first slice does not require preserving multiple same-day revisions as a first-class history concept

### 3. API Contract

The first admitted route is:

- `GET /api/metrics/urpd-features`

Response direction:

- latest materialized snapshot only
- response shape is a single metric object, consistent with existing `GET /api/metrics/*` latest-style routes rather than an array or envelope wrapper
- `404` when no materialized data exists
- `503` when the QuestDB repository is unavailable

This route is a metric/operator surface, not yet a bundle field and not yet an execution-grade input.

### 4. Source-of-Truth Rule

For this first slice:

- the feature contract is derived locally from repo-native `URPD` logic
- this does not claim exact equivalence to `BRK` `cost-basis` distribution semantics
- any future migration to `BRK`-derived production semantics requires an explicit comparison and freeze decision

This matches the broader rule already stated in `spec-052`: conceptually similar upstream analytics do not automatically replace local canonical semantics.

### 5. Backtest Boundary

This spec intentionally stops short of full backtest consumption.

What this spec includes:

- stable scalar features
- historical materialization
- latest-read serving contract

What remains open after this spec:

- historical feature loading in the backtest ingestion path
- signal generation rules built on top of these features
- comparative validation of local-vs-`BRK` semantics

## Functional Requirements

### FR1: No Raw Histogram Promotion

The first promoted surface MUST be scalarized. Raw `URPD` buckets MUST NOT become the admitted first-slice route.

### FR2: Small Frozen Field Set

The first serving-grade contract MUST expose only the five named scalar feature fields plus supporting metadata.

### FR3: Persistent History

The feature set MUST be materialized into QuestDB rather than computed only request-time.

### FR4: Latest Route

The repo MUST expose a latest-read route for the materialized feature set under `/api/metrics/urpd-features`.

### FR5: Explicit Source Boundary

The spec MUST state that this first slice is locally derived and does not silently reclassify `BRK` as the canonical source.

### FR6: Backtest Follow-Up Is Separate

The first slice MUST NOT pretend that historical backtest ingestion is complete until the loader path is explicitly wired.

## Acceptance Direction

This spec is complete only when all of the following are true:

1. the five canonical feature fields are frozen
2. a QuestDB daily table exists for the feature set
3. the latest route is served and tested
4. the materialization path writes the feature set during the daily holder/cohort pass
5. the remaining backtest integration work is explicitly recorded as follow-up rather than implied complete
