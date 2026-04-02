# Feature Service Admission Gate

Date: 2026-04-02

Status: Post-`M6` governance baseline for any future research-to-production promotion

Scope:

- `nupl_surface`
- `cost_basis_surface`

Explicitly out of scope:

- `reserve-risk` until placeholder/default internals are removed from the calculator

## 1. Summary Decision

`M6` made `/api/metrics/nupl` and `/api/metrics/cost-basis` live as `tier_3_research` surfaces.

That runtime availability does not authorize downstream admission by itself.

Current freeze:

| Surface | Runtime state after `M6` | Admission state | Gate required before any future promotion |
|------|------|------|------|
| `nupl_surface` | live DuckDB-backed route | keep `tier_3_research` | external validation evidence plus explicit field-level policy for the estimated `pct_supply_in_profit` field |
| `cost_basis_surface` | live DuckDB-backed route | keep `tier_3_research` | consumer-use-case freeze plus reproducibility and operator acceptance checks |
| `reserve-risk` | registered but returns `501` | not a candidate here | separate hardening milestone removes placeholder/default internals first |

## 2. Core Principle

A research route does not become part of a consumer contract just because it is live.

Future admission must be justified by:

1. stable route behavior
2. stable field semantics
3. explicit validation evidence
4. explicit consumer-use approval

## 3. Route-Specific Gates

### `nupl_surface`

Required before any promotion beyond `tier_3_research`:

1. preserve or narrow the explicit estimate semantics for `pct_supply_in_profit`
2. freeze whether the estimated field is:
   - excluded from the admitted slice, or
   - admitted only with explicit `is_estimated` metadata
3. require validation evidence for core `nupl` itself, not just endpoint liveness

Current validation signal already present in repo:

- [tests/validation/test_rbn_validation.py](/media/sam/1TB/UTXOracle/tests/validation/test_rbn_validation.py) includes `TestNUPLValidation::test_nupl_correlation_with_rbn`

Current route semantics already frozen in runtime:

- `200` when the latest DuckDB snapshot has usable realized-cap and market-cap inputs
- `503` when the DuckDB file is missing
- `404` when schema/tables are missing or the current snapshot is unusable

Candidate future admitted subset:

- `nupl`
- `zone`
- `market_cap_usd`
- `realized_cap_usd`
- `unrealized_profit_usd`
- `confidence`
- `block_height`
- `timestamp`

Fields that remain research-only until explicitly re-decided:

- `pct_supply_in_profit`
- `pct_supply_in_profit_is_estimated`
- `pct_supply_in_profit_method`

No-go conditions:

- external validation for core `nupl` is unavailable or fails
- any consumer contract treats `pct_supply_in_profit` as a direct profit-state measurement
- runtime and consumer docs disagree on estimated-field semantics

Implication:

- `nupl` has a credible path to future admission
- the estimated `pct_supply_in_profit` field is the gating semantic risk

### `cost_basis_surface`

Required before any promotion beyond `tier_3_research`:

1. freeze the intended consumer use case
2. freeze the admitted field subset if the full route is not needed
3. define reproducibility checks that do not depend on external parity data
4. confirm operator acceptance for current-state DuckDB serving semantics

Current evidence already present in repo:

- [scripts/metrics/cost_basis.py](/media/sam/1TB/UTXOracle/scripts/metrics/cost_basis.py) is direct DuckDB cohort math without placeholder constants
- [tests/test_cost_basis.py](/media/sam/1TB/UTXOracle/tests/test_cost_basis.py) and [tests/test_api_wave2_metrics.py](/media/sam/1TB/UTXOracle/tests/test_api_wave2_metrics.py) cover route behavior and degraded semantics

Current route semantics already frozen in runtime:

- `200` when the latest DuckDB snapshot has usable cohort cost-basis state
- `503` when the DuckDB file is missing
- `404` when schema/tables are missing or the current snapshot has no usable cost-basis data

Candidate future admitted subset:

- `sth_cost_basis`
- `lth_cost_basis`
- `total_cost_basis`
- `sth_mvrv`
- `lth_mvrv`
- `current_price_usd`
- `block_height`
- `timestamp`
- `confidence`

Fields that should stay optional or research-only unless a consumer explicitly needs them:

- `sth_supply_btc`
- `lth_supply_btc`

No-go conditions:

- consumer use remains underspecified
- reproducibility checks are not published
- cohort-boundary semantics (`155` days / `22,320` blocks) are not frozen in admission docs

Implication:

- `cost-basis` is the strongest candidate for future promotion
- but it still lacks the external-validation-style evidence that already exists for `nupl`

### `reserve-risk`

`reserve-risk` is excluded from this gate.

Reason:

- the calculator still mixes real reads with placeholder/default internals
- this is a hardening problem first, not an admission problem

## 4. Candidate Outcomes

`M7` should decide one of these explicitly:

1. keep both routes as `tier_3_research`
2. promote only `cost_basis_surface`
3. promote only a reduced `nupl_surface` field subset
4. promote both, but with route-specific caveats and field policies

The default if evidence is incomplete is:

- keep the route `tier_3_research`

## 5. Admission Evidence Classes

Every future promotion decision should cite all applicable evidence classes:

| Evidence class | `nupl_surface` | `cost_basis_surface` |
|------|------|------|
| runtime wiring and degraded semantics | required | required |
| contract field policy | required | required |
| external validation parity | strongly preferred; already has a repo path | optional if no credible reference exists |
| operator reproducibility | required | required |
| consumer-use statement | required | required |

Mandatory evidence today:

- `nupl_surface`: runtime semantics, consumer field policy, named validation path, operator reproducibility
- `cost_basis_surface`: runtime semantics, consumer field policy, operator reproducibility, consumer-use statement

Optional evidence today:

- external parity for `cost_basis_surface` if a credible reference later exists

## 6. M7 Exit Criteria

`M7` is complete only when:

1. `nupl_surface` has an explicit go/no-go decision beyond research tier
2. `cost_basis_surface` has an explicit go/no-go decision beyond research tier
3. any admitted field subset is frozen in the consumer contract docs
4. `reserve-risk` is kept out of scope or moved into a separate hardening plan

If `M7` promotes nothing, that is still a valid completion state as long as the reasons are explicit.
