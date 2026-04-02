# Feature Service Wave 2 Decision

Date: 2026-04-02

Status: Historical `M5` decision package for Wave 2 of spec-046

Historical note:

- this document captures the pre-implementation freeze used to start `M6`
- runtime and contract truth after `M6` now live in the roadmap, contract registry, and provenance manifest
- a later metric source-of-truth freeze also made `reserve-risk` a `BRK`-first overlapping metric, so this document should not be read as an instruction to resume local productization by default

Scope:

- `/api/metrics/reserve-risk`
- `/api/metrics/nupl`
- `/api/metrics/cost-basis`

## 1. Summary Decision

| Route | Calculator state | API state | Decision |
|------|------|------|------|
| `/api/metrics/reserve-risk` | partial calculator with placeholder/default internals | registered, returns `501` | hold out of the next promotion milestone |
| `/api/metrics/nupl` | real calculator with one approximated output field | registered, returns `501` | shortlist for the next selective promotion milestone |
| `/api/metrics/cost-basis` | real calculator with stable DuckDB inputs | registered, returns `501` | shortlist for the next selective promotion milestone |

## 2. Route Audit

### `/api/metrics/reserve-risk`

Evidence in code:

- [scripts/metrics/reserve_risk.py](/media/sam/1TB/UTXOracle/scripts/metrics/reserve_risk.py) uses `mvrv = 1.5` as a hardcoded placeholder
- [scripts/metrics/reserve_risk.py](/media/sam/1TB/UTXOracle/scripts/metrics/reserve_risk.py) falls back to `liveliness = 0.3` when `cointime_metrics` is absent
- [scripts/metrics/reserve_risk.py](/media/sam/1TB/UTXOracle/scripts/metrics/reserve_risk.py) falls back to `reserve_risk = 0.001` when no usable HODL Bank or supply exists

Decision:

- do not promote in the next slice
- keep the route registered but placeholder (`501`) until hardcoded and default analytical internals are removed

Reason:

- this route fails spec-046 FR4 (`No Placeholder Promotion`)
- wiring it now would expose a signal that still mixes real data with placeholder internals

### `/api/metrics/nupl`

Evidence in code:

- [scripts/metrics/nupl.py](/media/sam/1TB/UTXOracle/scripts/metrics/nupl.py) calculates realized cap and unspent supply from DuckDB-backed realized metrics helpers
- zone classification is real and deterministic
- `pct_supply_in_profit` is currently an approximation derived from NUPL, not a direct per-UTXO profit-state calculation

Decision:

- treat as a selective Wave 2 promotion candidate
- require route-level wiring plus explicit contract wording that `pct_supply_in_profit` is an estimate unless the field is renamed or replaced

Reason:

- the core signal is analytically real
- the main remaining risk is contract semantics on the estimated field, not placeholder math across the whole route

### `/api/metrics/cost-basis`

Evidence in code:

- [scripts/metrics/cost_basis.py](/media/sam/1TB/UTXOracle/scripts/metrics/cost_basis.py) computes STH/LTH cost basis directly from `utxo_lifecycle_full`
- cohort boundary is explicit (`155` days / `22,320` blocks)
- STH and LTH MVRV are derived directly from current price versus cohort cost basis

Decision:

- treat as the strongest selective Wave 2 promotion candidate
- keep route placeholder (`501`) until route wiring and route-level degraded semantics are implemented

Reason:

- the calculator is materially closer to productization than `reserve-risk`
- the remaining work is mainly serving-path and route-contract work, not analytical redefinition

## 3. Test Signal

Audit-time checks on 2026-04-02:

- `pytest -q tests/test_reserve_risk.py` -> `13 passed`
- `pytest -q tests/test_nupl.py` -> `19 passed`
- `pytest -q tests/test_cost_basis.py` -> placeholder-route test corrected so the suite reflects the actual `501` state instead of assuming a promoted endpoint

Runtime contract checks added in `M5`:

- Wave 2 placeholder routes now return `501` cleanly without depending on unrelated app state
- route tests now reflect current reality instead of pre-promoting the API surface in test code

## 4. Resulting Freeze

`M5` is complete when interpreted as a decision milestone:

- `reserve-risk` is explicitly held with blockers
- `nupl` is explicitly shortlisted for the next selective promotion milestone
- `cost-basis` is explicitly shortlisted for the next selective promotion milestone

This turns Wave 2 from an all-or-nothing bucket into a selective next slice.

## 5. Next Milestone

Recommended `M6` scope:

- implement `/api/metrics/nupl`
- implement `/api/metrics/cost-basis`
- keep `/api/metrics/reserve-risk` outside the promotion slice until placeholder internals are removed

`M6` should also define:

- route-level `404` / `503` semantics for the two promoted routes
- RED tests for healthy and degraded cases
- final field policy for NUPL's `pct_supply_in_profit`
