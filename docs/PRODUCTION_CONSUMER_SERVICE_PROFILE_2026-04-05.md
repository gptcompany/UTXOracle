# Production Consumer Service Profile

Date: 2026-04-07

Status: Current service-consumption decision after the `:8011` promotion pass, Wave 1 materialization, the metric source-of-truth freeze, and the spec-052 introduction of btc feature bundles and signal snapshots.

Purpose:

- define what the repo should be treated as when consumed automatically in a pipeline
- separate the production-ready consumer surface from research and validation surfaces
- classify the most interesting remaining metric families by the correct next action

Scope note:

- this profile is broader than the original narrow `v1` live-only slice in [docs/NAUTILUS_FEATURE_CONTRACT_V1.md](/media/sam/1TB/UTXOracle/docs/NAUTILUS_FEATURE_CONTRACT_V1.md)
- it answers the practical question "what can an automatic downstream consumer safely ingest today?"

Primary references:

- [docs/FEATURE_CONTRACT_REGISTRY.md](/media/sam/1TB/UTXOracle/docs/FEATURE_CONTRACT_REGISTRY.md)
- [docs/PRODUCTION_SURFACE_DISPOSITION_2026-04-02.md](/media/sam/1TB/UTXOracle/docs/PRODUCTION_SURFACE_DISPOSITION_2026-04-02.md)
- [docs/METRIC_SOURCE_OF_TRUTH_MANIFEST.md](/media/sam/1TB/UTXOracle/docs/METRIC_SOURCE_OF_TRUTH_MANIFEST.md)
- [docs/NAUTILUS_FEATURE_CONTRACT_V1.md](/media/sam/1TB/UTXOracle/docs/NAUTILUS_FEATURE_CONTRACT_V1.md)

## 1. Service Definition

Treat the repo as a production-ready upstream feature service only under this shape:

- `:8011` = canonical consumer API
- `QuestDB` = serving plane for production-consumable families
- `:8001` = research, operator, validation, and transition app
- `BRK` = upstream source for overlapping shared macro metrics

Practical rule:

- if a feature family is part of the production consumer service, it must be consumable from a stable route family with explicit failure semantics
- if a family is still calculator-heavy, mixed, or upstream-validation-oriented, it stays outside the production consumer service even if code exists

## 2. Production-Ready Consumer Bundles

These are the families that should be treated as production-ready and safe for automatic downstream consumption today.

### Core live bundle (`tier_1_execution` / `tier_2_operator`)

- `/api/v1/live/*`
- `/api/v1/charts/*`
- `/api/prices/*`
- `/api/metrics/latest`

Role:

- shortest-path consumer bundle for live polling, health gating, and compact market-state ingestion

### Event and forensics bundle (`tier_2_operator`)

- `/api/whale/{transactions,summary,transaction/{txid}}`

Role:

- canonical event bundle for whale-driven flows
- `entity` enrichment is additive and optional; the base event remains valid without enrichment

### Daily cohort bundle (`tier_2_operator`)

- `/api/metrics/address-cohorts`
- `/api/metrics/wallet-waves`
- `/api/metrics/absorption-rates`

Role:

- production-consumable daily analytical bundle for cohort and holder-state features
- latest snapshots are in scope; `wallet-waves/history` is not

### BTC Consumer Feature Bundles (`tier_1_execution`)

- `/api/features/btc/core/{latest,history}`
- `/api/features/btc/flow/{latest,history}`
- `/api/features/btc/macro/{latest,history}`
- `/api/features/btc/cohort/{latest,history}`

Role:

- structured and admitted downstream consumer feature contracts (spec-052)
- aggregates underlying metrics into stable bounded interfaces for strategy consumption

### BTC Signal Snapshot (`tier_1_execution`)

- `/api/signals/btc/{latest,history}`

Role:

- the canonical deterministic layer aggregating the four feature bundles into normalized bounded bias, conviction, and flow/regime/valuation scores (spec-052)

## 3. Classification For The Remaining Interesting Families

| Family | Classification | Decision |
|------|------|------|
| `NUPL` | `consume_from_brk` | keep the local route research-only; any future production/shared consumption should normalize from `BRK` |
| `cost_basis` | `promote_next_local_candidate` | strongest repo-native next promotion candidate after field-subset freeze and reproducibility checks |
| `wallet/cohort` | `admit_now_in_service_profile` | treat the latest QuestDB-backed `address-cohorts`, `wallet-waves`, and `absorption-rates` routes as part of the production consumer service |
| `advanced research` | `split_selectively` | do not promote the bucket as a whole; only reopen individual families such as `cointime` through a dedicated hardening/promotion decision |
| `RBN validation` | `keep_ops_only` | useful for validation and operator workflows, but not part of the production consumer feature plane |

## 4. What This Means In Practice

### `NUPL`

`NUPL` remains analytically useful, but it should not be promoted as a local production route by default.

Reason:

- the metric source-of-truth policy is already `BRK`-first for future shared or admitted consumption
- the local route still carries the explicit estimated-field caveat on `pct_supply_in_profit`

Correct use:

- consume `NUPL` from `BRK` for production/shared macro use
- keep the local route for research, validation, and custom experimentation

### `cost_basis`

`cost_basis` is the strongest local candidate for the next service expansion.

Reason:

- it is repo-native
- it is not superseded by a stronger named upstream equivalent
- it already has credible implementation and route semantics

Correct next action:

- freeze the consumer field subset
- publish reproducibility checks
- then promote it as a dedicated production-consumable family

### `wallet/cohort`

`wallet/cohort` is no longer just a research curiosity. The latest snapshot routes are already materialized and served from QuestDB on `:8011`.

Correct interpretation:

- `address-cohorts`, `wallet-waves`, and `absorption-rates` belong to the production-ready service profile
- `wallet-waves/history` does not

### `advanced research`

The bucket is too mixed to promote wholesale.

Correct interpretation:

- leave the mixed bucket research-only
- reopen only a specific family with its own service contract, provenance, and failure semantics

### `RBN validation`

`RBN` remains a validation and formula-alignment tool, not a downstream feature family.

Correct interpretation:

- useful for validation, parity checks, and operator workflows
- not part of the machine-consumable production feature plane

## 5. Consumer Rule Of Thumb

If a downstream wants a production-ready automatic pipe today, the default stack should be:

1. `:8011` core live bundle
2. `:8011` whale query bundle
3. `:8011` daily cohort bundle
4. `BRK` for overlapping shared macro metrics such as `NUPL`, `SOPR`, `liveliness`, and `reserve_risk`

The default stack should not be:

- arbitrary `:8001` research routes
- the full `BRK` metric universe
- mixed advanced research families without a narrowed contract

## 6. Final Decision

The production-ready consumer service is now defined as:

- canonical live bundle on `:8011`
- canonical whale/event bundle on `:8011`
- canonical daily cohort bundle on `:8011`
- `BRK` for overlapping shared macro metrics

The next local expansion target is:

- `cost_basis`

The families that remain intentionally outside the production consumer service are:

- local `NUPL`
- mixed advanced research routes
- `RBN` validation
