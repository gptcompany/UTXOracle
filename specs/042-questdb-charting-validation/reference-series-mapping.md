# spec-042 Reference Series Mapping

## Purpose

This file freezes which chart families can be compared only against internal live references,
and which datasets have a credible BRK / CheckOnChain-style external mapping.

The goal is to avoid forcing an external comparison path where the semantics do not match.

## Current Rule

`live-price-comparison` is an operational market-reference chart.

It is valid to compare:

- `utxoracle_price` vs `mempool_exchange_price`
- `utxoracle_price` vs `hyperliquid_oracle_price`
- `utxoracle_price` vs `hyperliquid_mark_price`

These are all same-domain market price references already present in `live_snapshots`.

It is **not** valid to compare `live-price-comparison` directly against:

- `CheckOnChain`
- `BRK realized price`
- `BRK liveliness`
- `BRK reserve risk`

Reason:

- those external series are not spot-market reference prices
- they represent structural on-chain metrics, not live execution/reference venue prices
- a numerical diff would look precise but be semantically meaningless

## Curated BRK Fields Already Present In `live_snapshots`

The live runtime already carries these BRK-derived curated fields:

- `features.brk_realized_price`
- `features.brk_liveliness`
- `features.brk_reserve_risk`

These fields are the first credible bridge to BRK / CheckOnChain-style validation.

## External Mapping Candidates

### 1. `brk_realized_price`

Candidate chart family:

- `realized-price-reference`

Local / upstream mapping:

- local field: `features.brk_realized_price`
- BRK semantic: `realized_price_usd`
- closest CheckOnChain-style reference: `realised_price`

Notes:

- this is the strongest first external mapping candidate
- it is a better external-validation target than `live-price-comparison`
- the chart is expected to be slow-moving and nearly flat over short live windows

### 2. `brk_liveliness`

Candidate chart family:

- `liveliness-reference`

Local / upstream mapping:

- local field: `features.brk_liveliness`
- BRK semantic: `liveliness`
- closest CheckOnChain-style reference: `liveliness`

Notes:

- semantically valid, but less useful as the first visual validation slice than realized price

### 3. `brk_reserve_risk`

Candidate chart family:

- `reserve-risk-reference`

Local / upstream mapping:

- local field: `features.brk_reserve_risk`
- BRK semantic: `reserve_risk`
- closest CheckOnChain-style reference: `reserve_risk`

Notes:

- semantically valid
- likely needs clearer tolerance handling because the metric can be small in absolute terms

## Admitted Compare Modes

### Admitted now

- `live-price-comparison`
  - compare scope: internal live references only
  - baseline set: mempool + Hyperliquid
  - no external parity claim
- `realized-price-reference`
  - compare scope: local `features.brk_realized_price` vs live BRK curated `realized_price_usd`
  - baseline set: current BRK curated feature snapshot
  - failure mode: degrade to `no_overlap` after a `2s` hard-timeout path instead of failing the chart API

### Not admitted yet

- BRK / CheckOnChain external compare mode for `live-price-comparison`
- any generic “compare any chart to any external source” engine

## Recommended Next External Validation Slice

The safest first external-validation slice is:

1. keep `realized-price-reference` narrow and operational
2. run parity samples and record artifacts for the BRK-backed compare output
3. add visual review only on top of that numeric output
4. defer any generic external overlay engine until more than one external family is real
