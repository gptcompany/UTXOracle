# UTXOracle Metric Source of Truth Manifest

Date: 2026-04-05

Status: Updated metric-level source-of-truth baseline after explicit BRK-first choice for overlapping macro analytics

Machine-readable source of truth:

- [docs/contracts/metric_source_of_truth_manifest.yaml](/media/sam/1TB/UTXOracle/docs/contracts/metric_source_of_truth_manifest.yaml)

Primary inputs:

- [docs/LIVE_STACK_ROLE_MATRIX.md](/media/sam/1TB/UTXOracle/docs/LIVE_STACK_ROLE_MATRIX.md)
- [docs/FEATURE_SERVICE_ROADMAP_PREP_2026-04-01.md](/media/sam/1TB/UTXOracle/docs/FEATURE_SERVICE_ROADMAP_PREP_2026-04-01.md)
- [docs/FEATURE_SERVICE_ROADMAP_2026-04-01.md](/media/sam/1TB/UTXOracle/docs/FEATURE_SERVICE_ROADMAP_2026-04-01.md)
- [scripts/live/source_clients.py](/media/sam/1TB/UTXOracle/scripts/live/source_clients.py)

## 1. Purpose

This manifest freezes a simple engineering rule:

- do not productize a local metric route by default if an upstream already owns the shared metric semantics and the repo has no clear reason to diverge

This is a metric-level policy, not a route inventory.

Use it to answer:

- should this metric be adopted from `BRK`?
- should it stay repo-local?
- should a local implementation remain research-only?
- should duplicate local productization work be discarded?

## 2. Decision Vocabulary

- `local_canonical`: `UTXOracle` owns the metric and downstream contract
- `adopt_from_brk`: `BRK` is the preferred production source; `UTXOracle` should consume/normalize rather than re-implement by default
- `local_research_only`: local implementation is allowed for research, validation, or custom variants, but is not the default production source
- `hold_pending_explicit_source_decision`: do not promote the local implementation until a written `BRK` vs local decision exists

## 3. Scope Note

This first pass is intentionally narrow. It covers the metrics that are currently driving roadmap friction or duplication risk:

- `utxoracle_price`
- `realized_price_usd`
- `liveliness`
- `sopr`
- `reserve_risk`
- `nupl`
- `cost_basis`

It does not yet reclassify every overlapping metric family already exposed on `:8001`.

## 4. Metric Decision Table

| Metric family | Preferred production source of truth | Current UTXOracle role | Current runtime status | Policy | Immediate rule |
|------|------|------|------|------|------|
| `utxoracle_price` | `UTXOracle` | canonical repo-native on-chain price | admitted live metric on `:8011` | `local_canonical` | never replace with `BRK` or another upstream price metric |
| `realized_price_usd` | `BRK` | adopted upstream in the live feature plane and chart comparisons | consumed through the curated `BRK` subset | `adopt_from_brk` | do not open a new local productization track for this metric by default |
| `liveliness` | `BRK` for the shared live feature plane | local cointime logic remains valid for research and validation | consumed through the curated `BRK` subset; repo-local cointime routes remain separate | `adopt_from_brk` | do not create a second admitted consumer route for the same shared signal without an explicit contract reason |
| `sopr` | `BRK` for any future shared or admitted signal | local DuckDB route may remain available for research, validation, and legacy consumers | `/api/metrics/sopr` still exists on `:8001` today, but is not the preferred long-term shared source | `adopt_from_brk` | do not expand local productization of SOPR by default; future contract work should normalize from `BRK` unless a deliberately different local variant is approved |
| `reserve_risk` | `BRK` | local calculator may exist for validation or experiments, but not as the default shared feature source | shared live feature already comes from `BRK`; `/api/metrics/reserve-risk` remains excluded from local productization | `adopt_from_brk` | discard local route-productization work by default; reopen only if `BRK` adoption is blocked or an explicitly different local methodology is approved |
| `nupl` | `BRK` for any future shared or admitted signal | local DuckDB-backed route remains useful for research, validation, and custom experimentation | `/api/metrics/nupl` is live as `tier_3_research` | `adopt_from_brk` | keep the local route research-only by default; any future admitted signal should normalize from `BRK` unless a deliberately reduced local contract is approved |
| `cost_basis` | `UTXOracle` DuckDB | repo-native cohort and cost-basis analytics | `/api/metrics/cost-basis` is live as `tier_3_research` | `local_canonical` | keep local ownership unless an exact upstream equivalent is named, verified, and contractually frozen |

## 5. Governance Rules

1. If `BRK` already exposes a metric family with acceptable semantics, no new local promotion work should start until the repo explains why a local variant is necessary.
2. `electrs` is infra, not an analytical metric source of truth. It may support sync or validation, but it should not be named as the canonical source for metrics like `reserve_risk`, `sopr`, `nupl`, or `cost_basis`.
3. Research routes may continue to exist locally even when `BRK` is preferred, but that does not imply production admission.
4. Any future reopening of `reserve-risk`, `sopr`, or `nupl` admission must update:
   - [docs/METRIC_SOURCE_OF_TRUTH_MANIFEST.md](/media/sam/1TB/UTXOracle/docs/METRIC_SOURCE_OF_TRUTH_MANIFEST.md)
   - [docs/contracts/metric_source_of_truth_manifest.yaml](/media/sam/1TB/UTXOracle/docs/contracts/metric_source_of_truth_manifest.yaml)
   - [docs/FEATURE_SERVICE_ROADMAP_2026-04-01.md](/media/sam/1TB/UTXOracle/docs/FEATURE_SERVICE_ROADMAP_2026-04-01.md)
   - [docs/FEATURE_CONTRACT_REGISTRY.md](/media/sam/1TB/UTXOracle/docs/FEATURE_CONTRACT_REGISTRY.md)
   - [docs/NAUTILUS_FEATURE_CONTRACT_V1.md](/media/sam/1TB/UTXOracle/docs/NAUTILUS_FEATURE_CONTRACT_V1.md)

## 6. Immediate Consequence

As of this baseline:

- local `reserve-risk` productization is not the default next step
- local `sopr` productization is not the default next step for any future shared contract work
- local `nupl` productization is not the default next step for any future shared contract work
- `reserve-risk` should be treated as a `BRK`-first overlapping metric
- `sopr` should be treated as a `BRK`-first overlapping metric for future contract direction
- `nupl` should be treated as a `BRK`-first overlapping metric for future contract direction
- Wave 1 history/materialization debt and any future admission work for `cost-basis` or `nupl` are higher-value local engineering slices than duplicating `reserve-risk` locally
