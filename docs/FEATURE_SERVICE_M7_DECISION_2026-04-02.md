# Feature Service M7 Decision

Date: 2026-04-02

Status: Final `M7` decision package for post-`M6` research-to-production admission

Decision outcome:

- no promotion beyond `tier_3_research` is approved today for either `nupl_surface` or `cost_basis_surface`
- `reserve-risk` remains outside this decision and stays outside the current admission track; later source-of-truth governance makes it `BRK`-first by default

## 1. Final Decision Table

| Surface | Current runtime state | M7 decision | Why |
|------|------|------|------|
| `nupl_surface` | live DuckDB-backed research route | no-go for promotion today | core signal has a validation path, but the estimated `pct_supply_in_profit` field still creates a consumer-contract risk unless a reduced subset or explicit estimated-field contract is chosen |
| `cost_basis_surface` | live DuckDB-backed research route | no-go for promotion today | calculator and runtime are strong, but consumer use and reproducibility evidence are not yet frozen tightly enough for admission |
| `reserve-risk` | registered `501` research route | out of scope | not part of this admission review and now additionally frozen behind a `BRK`-first source-of-truth decision |

## 2. Route Notes

### `nupl_surface`

What is good enough already:

- route behavior and degraded semantics are frozen
- core `nupl` has a repo-native validation path
- the route explicitly marks `pct_supply_in_profit` as estimated

Why the answer is still no-go:

- the current route payload mixes a candidate core signal with an estimated auxiliary field
- no consumer-facing subset has yet been frozen beyond research
- admission today would create unnecessary ambiguity for downstream feature use

What would reopen the decision:

- a reduced admitted subset that excludes the estimated field, or
- an explicit consumer contract that keeps the field and declares it estimated

### `cost_basis_surface`

What is good enough already:

- no placeholder math is involved in the current calculator
- route behavior and degraded semantics are frozen
- the metric family is interpretable for macro holder positioning and support/resistance logic

Why the answer is still no-go:

- the exact downstream use case has not been frozen
- the reproducibility package is still implicit in code/tests rather than published as an operator-facing admission artifact
- promotion pressure is lower than the cost of admitting a route by convention

What would reopen the decision:

- a published reproducibility note
- an explicit admitted field subset or consumer-use statement

## 3. Ranking For Future Reconsideration

If future work wants to reopen admission:

1. `cost_basis_surface` is the first candidate
2. a reduced `nupl_surface` slice is the second candidate
3. `reserve-risk` remains blocked unless a later source-of-truth decision explicitly approves a non-duplicative local path

## 4. Immediate Follow-Up

The next substantive engineering choices are:

1. reopen `reserve-risk` only if the source-of-truth manifest is intentionally superseded and a `BRK` adoption path or explicit local-variant rationale is written down
2. publish a reproducibility note for `cost_basis_surface` only if future contract admission is truly desired
3. refresh and publish explicit validation evidence for `nupl_surface` only if future contract admission is truly desired

Until then, the runtime and contract truth remains:

- `nupl_surface`: live, `tier_3_research`
- `cost_basis_surface`: live, `tier_3_research`
- `reserve-risk`: held at `501` and no longer a default local hardening target
