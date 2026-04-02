# UTXOracle Feature Service Roadmap

Date: 2026-04-02

Status: Execution roadmap updated after `M1`, `M2`, `M3`, `M4a`, `M4b`, `M5`, `M6`, `M7`, and the metric source-of-truth manifest freeze

Primary baseline:

- [docs/FEATURE_SERVICE_ROADMAP_PREP_2026-04-01.md](/media/sam/1TB/UTXOracle/docs/FEATURE_SERVICE_ROADMAP_PREP_2026-04-01.md)
- [docs/METRIC_SOURCE_OF_TRUTH_MANIFEST.md](/media/sam/1TB/UTXOracle/docs/METRIC_SOURCE_OF_TRUTH_MANIFEST.md)
- [docs/SCOPE_LOCK_2026-04-02.md](/media/sam/1TB/UTXOracle/docs/SCOPE_LOCK_2026-04-02.md)
- [docs/PRODUCTION_SURFACE_DISPOSITION_2026-04-02.md](/media/sam/1TB/UTXOracle/docs/PRODUCTION_SURFACE_DISPOSITION_2026-04-02.md)

Primary execution specs:

- [specs/044-feature-service-contract-registry/spec.md](/media/sam/1TB/UTXOracle/specs/044-feature-service-contract-registry/spec.md)
- [specs/045-feature-dependency-provenance-manifest/spec.md](/media/sam/1TB/UTXOracle/specs/045-feature-dependency-provenance-manifest/spec.md)
- [specs/046-calculator-surface-productization/spec.md](/media/sam/1TB/UTXOracle/specs/046-calculator-surface-productization/spec.md)
- [specs/047-whale-entity-surface-unification/spec.md](/media/sam/1TB/UTXOracle/specs/047-whale-entity-surface-unification/spec.md)
- [specs/048-implemented-route-hardening/spec.md](/media/sam/1TB/UTXOracle/specs/048-implemented-route-hardening/spec.md)
- [specs/049-feature-research-admission-gate/spec.md](/media/sam/1TB/UTXOracle/specs/049-feature-research-admission-gate/spec.md)
- [specs/050-canonical-8011-promotion/spec.md](/media/sam/1TB/UTXOracle/specs/050-canonical-8011-promotion/spec.md)

## 1. Roadmap Objective

Turn `UTXOracle` from a mixed inventory of live routes, implemented routes, calculator-backed research code, and placeholders into a deliberate upstream feature service for `nautilus_dev`.

This roadmap does not try to:

- expose every metric
- replace `BRK`
- turn `UTXOracle` into a trading engine

It does aim to:

- define a real consumer contract
- harden currently exposed routes that are still caveated
- productize the highest-value calculator-backed surfaces
- unify whale and future entity-aware surfaces

## 2. Planning Assumptions

This roadmap assumes the verified state captured on 2026-04-01:

- `:8011` is the canonical and only supported live consumer host today
- `:8001` remains mixed legacy/main-app surface
- some implemented routes were exposed with hardcoded or partial placeholder behavior before `M2`
- several high-value analytics still return `501`, but Wave 1 balance/holder routes are now promoted

Operational assumption:

- the roadmap should optimize first for contract clarity and operational truth, then for breadth of feature exposure

## 3. North Star

By the end of this roadmap, `UTXOracle` should provide:

1. one explicit feature contract for `nautilus_dev`
2. one dependency/provenance manifest for operators and consumers
3. no admitted route families with hidden mocked inputs or hidden hardcoded baselines
4. at least one promoted wave of calculator-backed analytics
5. one canonical whale surface with entity-ready foundations

## 4. Priority Rules

Priority is driven by downstream utility and contract risk, not by novelty.

Highest priority:

- contract clarity
- provenance clarity
- removal of overstated implemented routes
- promotion of analytics that are already valuable and already close to wired

Lower priority:

- wider research metric fanout
- deeper entity attribution
- full coverage of all historical families

Scope lock:

- new implementation work must strengthen the canonical `:8011` contract, extend repo-specific analytics not cleanly covered by `BRK`, or extend whale/entity forensics
- `:8001` existence alone is not a reason to widen the production boundary
- overlapping macro metrics should not reopen local productization by default while the metric source-of-truth manifest remains active
- route-family disposition between `:8001`, `:8011`, `QuestDB`, `DuckDB`, and `BRK` should follow [docs/PRODUCTION_SURFACE_DISPOSITION_2026-04-02.md](/media/sam/1TB/UTXOracle/docs/PRODUCTION_SURFACE_DISPOSITION_2026-04-02.md)

## 5. Roadmap Matrix

| Surface | Current state | Primary consumer | Source of truth | Blocking gap | Target contract state | Priority | Spec |
|--------|---------------|------------------|-----------------|--------------|-----------------------|----------|------|
| `/api/v1/live/*` | runtime verified on dedicated live host only | `nautilus_dev` | live app + live worker | resolved in `M2`; keep host policy frozen | tier-1 contract on one canonical host | P0 | spec-048 |
| `/api/v1/charts/*` | runtime verified | `nautilus_dev`, research | live app + live worker | contract registration | admitted companion live surface | P1 | spec-044 |
| `/api/prices/*` | code implemented and contract-registered | `nautilus_dev`, research | QuestDB | no structural blocker; freshness remains operational concern | tier-1 admitted price family | P0 | spec-044, spec-045 |
| `/api/whale/transactions`, `/summary`, `/transaction/{txid}` | code implemented; canonicalized in `M4a` with additive `whale_event.v1` in `M4b` | research, future forensics | QuestDB `mempool_predictions` + optional `address_clusters` enrichment | consumers still depend on table freshness and best-effort enrichment omission rules | canonical whale surface frozen with entity foundation fields | P1 | spec-047 |
| `/api/metrics/latest` | code implemented and contract-registered | `nautilus_dev`, research | QuestDB | no structural blocker; freshness remains operational concern | tier-1 admitted bundle | P1 | spec-044, spec-045 |
| `PRO Risk` | runtime-demoted; only `/zones` remains live metadata | research only today | mixed / placeholder inputs | real component inputs and historical serving are still absent | remain demoted until real implementation exists | P0 | spec-048 |
| `Puell Multiple` | runtime-demoted placeholder | research only today | computed inline | real 365d miner revenue history is still absent | remain demoted until real implementation exists | P0 | spec-048 |
| `address-cohorts` | code implemented | research, future trading features | DuckDB | contract admission decision only | promoted Wave 1 route | P1 | spec-046 |
| `wallet-waves` | code implemented | research, future trading features | DuckDB | current route is live; historical route still needs snapshot materialization | promoted Wave 1 route | P1 | spec-046 |
| `absorption-rates` | code implemented with on-demand historical reconstruction | research, future trading features | DuckDB + reconstructed baseline | persistent history/materialization is still pending | promoted Wave 1 route | P1 | spec-046 |
| `reserve-risk` | calculator only; intentionally held | research, macro/feature bundles | `BRK` for shared signal; local calculator only for validation/experiments unless separately approved | no explicit adopted `BRK`-backed contract path exists yet, and local duplication is not justified by default | remain excluded until a written `BRK` vs local decision is reopened | P2 | spec-046 |
| `nupl` | code implemented with explicit estimated-field contract | research, macro/feature bundles | DuckDB | still research-only; `pct_supply_in_profit` remains a declared estimate rather than a direct profit-state measurement | promoted selective Wave 2 route | P2 | spec-046 |
| `cost-basis` | code implemented | research, macro/feature bundles | DuckDB | still research-only; no `nautilus_dev` admission decision yet | promoted selective Wave 2 route | P2 | spec-046 |
| post-`M6` admission gate for `nupl` and `cost-basis` | not yet formalized before this roadmap update | `nautilus_dev`, operators | docs + validation evidence | no explicit route-to-consumer gate existed after selective Wave 2 wiring | formal go/no-go gate for any future `v2` promotion | P1 | spec-049 |
| feature contract registry | published | `nautilus_dev`, operators | docs + YAML | validation automation still missing | `v1` contract registry | P0 | spec-044 |
| dependency/provenance manifest | published | operators, consumers | docs + YAML | drift validation and optional metadata endpoint still missing | authoritative manifest | P0 | spec-045 |

## 6. Execution Tracks

### Track 0: Freeze the Contract Baseline

Outcome:

- the current verified state becomes the official planning baseline
- new route admission decisions stop being implicit

Work:

- preserve [docs/FEATURE_SERVICE_ROADMAP_PREP_2026-04-01.md](/media/sam/1TB/UTXOracle/docs/FEATURE_SERVICE_ROADMAP_PREP_2026-04-01.md) as the baseline source document
- treat specs `044`-`048` as the operative decomposition of this roadmap

### Track 1: Contract and Provenance First

Outcome:

- `UTXOracle` finally has a versioned feature contract and provenance manifest

Status:

- completed on 2026-04-01

Work:

- implement [spec-044](/media/sam/1TB/UTXOracle/specs/044-feature-service-contract-registry/spec.md)
- implement [spec-045](/media/sam/1TB/UTXOracle/specs/045-feature-dependency-provenance-manifest/spec.md)

Why first:

- without this track, all other work still lands into an ambiguous product surface

### Track 2: Harden Already Exposed Routes

Outcome:

- no admitted route remains admitted only because caveats are documented in markdown

Status:

- completed on 2026-04-01 via demotion of `PRO Risk` and `Puell Multiple`, route-order fix for power law, and singular live host policy

Work:

- implement [spec-048](/media/sam/1TB/UTXOracle/specs/048-implemented-route-hardening/spec.md)

Must resolve:

- `PRO Risk` keep-vs-demote
- `Puell Multiple` keep-vs-demote
- `/api/v1/models/power-law/predict` route shadowing
- `/api/v1/live/*` canonical host policy

### Track 3: Productize Wave 1 Calculators

Outcome:

- the first calculator-backed analytics leave the `501` bucket

Status:

- completed on 2026-04-01 for `address-cohorts`, `wallet-waves`, and `absorption-rates`
- `wallet-waves/history` remains explicitly outside the promoted slice

Work:

- implement Wave 1 of [spec-046](/media/sam/1TB/UTXOracle/specs/046-calculator-surface-productization/spec.md)

Wave 1 target set:

- `/api/metrics/address-cohorts`
- `/api/metrics/wallet-waves`
- `/api/metrics/absorption-rates`

### Track 4: Unify Whale and Entity Foundations

Outcome:

- `/api/whale` becomes a canonical surface instead of a mixed namespace
- entity foundations are defined only after route cleanup and namespace policy are stable

Status:

- `M4a` completed on 2026-04-01: canonical whale routes are frozen and legacy aliases now return explicit `410 Gone` migration stubs
- `M4b` completed on 2026-04-02: additive `whale_event.v1` fields and entity omission rules are now frozen for the canonical whale surface

Work:

- implement [spec-047](/media/sam/1TB/UTXOracle/specs/047-whale-entity-surface-unification/spec.md)

Execution note:

- route cleanup and canonicalization come first
- entity registry and enrichment foundations follow as a separate second slice inside the same track

### Track 5: Expand the Admitted Surface

Outcome:

- second-wave metric promotion begins only after the contract and hardening layers are stable
- the Wave 2 bucket is narrowed to routes that are analytically ready enough to justify real wiring

Status:

- `M5` completed on 2026-04-02 as a decision milestone
- `M6` completed on 2026-04-02 for `nupl` and `cost-basis`
- `nupl` and `cost-basis` are now live as research-only selective Wave 2 routes
- `reserve-risk` remains held outside the next promotion slice and is now frozen as a `BRK`-first overlapping metric rather than a default local hardening target

Work:

- Wave 2 and later waves from [spec-046](/media/sam/1TB/UTXOracle/specs/046-calculator-surface-productization/spec.md)
- decision package: [docs/FEATURE_SERVICE_WAVE2_DECISION_2026-04-02.md](/media/sam/1TB/UTXOracle/docs/FEATURE_SERVICE_WAVE2_DECISION_2026-04-02.md)

### Track 6: Govern Research-to-Production Admission

Outcome:

- post-`M6` research routes do not drift into downstream contracts by convention
- any promotion beyond `tier_3_research` is gated by explicit validation evidence and field-level policy

Status:

- completed on 2026-04-02 for the current post-`M6` candidate set
- `nupl` and `cost-basis` remain live but research-only after an explicit no-promotion decision

Work:

- implement [spec-049](/media/sam/1TB/UTXOracle/specs/049-feature-research-admission-gate/spec.md)
- freeze the admission gate in [docs/FEATURE_SERVICE_ADMISSION_GATE_2026-04-02.md](/media/sam/1TB/UTXOracle/docs/FEATURE_SERVICE_ADMISSION_GATE_2026-04-02.md)
- publish the current decision package in [docs/FEATURE_SERVICE_M7_DECISION_2026-04-02.md](/media/sam/1TB/UTXOracle/docs/FEATURE_SERVICE_M7_DECISION_2026-04-02.md)

Execution note:

- `nupl` and `cost-basis` being wired in `M6` does not imply future `nautilus_dev` admission
- `reserve-risk` remains out of scope for this track unless the source-of-truth manifest is explicitly reopened and approves either `BRK` adoption or an intentionally different local variant

## 7. Milestones and Dates

These are target windows, not guaranteed ship dates.

### Milestone M0: Baseline and Spec Freeze

Target window:

- 2026-04-01 to 2026-04-02

Exit criteria:

- roadmap baseline is frozen
- specs `044`-`048` exist and are accepted as the execution split

### Milestone M1: Contract and Provenance

Target window:

- 2026-04-03 to 2026-04-07

Includes:

- spec-044
- spec-045

Exit criteria:

- `docs/FEATURE_CONTRACT_REGISTRY.md` exists
- `docs/NAUTILUS_FEATURE_CONTRACT_V1.md` exists
- dependency/provenance manifest exists
- every P0 surface in this roadmap has an admission tier and backend class

Current status:

- completed on 2026-04-01

### Milestone M2: Hardening of Admitted Implemented Routes

Target window:

- 2026-04-08 to 2026-04-13

Includes:

- spec-048

Exit criteria:

- `PRO Risk` is either real or demoted
- `Puell Multiple` is either real or demoted
- power-law route-order conflict is removed
- live host policy is singular and documented

Current status:

- completed on 2026-04-01

### Milestone M3: Wave 1 Calculator Productization

Target window:

- 2026-04-14 to 2026-04-20

Includes:

- Wave 1 of spec-046

Exit criteria:

- `address-cohorts`, `wallet-waves`, and `absorption-rates` no longer return `501`, or are explicitly re-scoped with documented blockers

Current status:

- completed on 2026-04-01

### Milestone M4a: Whale Canonicalization

Target window:

- 2026-04-21 to 2026-04-25

Includes:

- first slice of spec-047

Exit criteria:

- canonical whale route family is frozen
- placeholder whale routes are removed, deprecated, or reimplemented

Current status:

- completed on 2026-04-01

### Milestone M4b: Entity Foundations

Target window:

- 2026-04-28 to 2026-05-02

Includes:

- second slice of spec-047

Exit criteria:

- minimum entity foundation schema exists
- entity provenance and confidence fields are frozen for future enrichment work

Current status:

- completed on 2026-04-02

### Milestone M5: Wave 2 Promotion Decision

Target window:

- 2026-05-05 to 2026-05-09

Includes:

- Wave 2 planning for spec-046

Exit criteria:

- `reserve-risk`, `nupl`, and `cost-basis` are either admitted into the next milestone or held with explicit blockers
- any required BRK cross-validation or confidence review is accounted for in the decision

Current status:

- completed on 2026-04-02
- `reserve-risk` held with explicit blockers
- `nupl` and `cost-basis` shortlisted for the next selective promotion milestone

### Milestone M6: Selective Wave 2 Productization

Target window:

- 2026-05-12 to 2026-05-18

Includes:

- selective Wave 2 implementation from spec-046

Exit criteria:

- `/api/metrics/nupl` and `/api/metrics/cost-basis` either stop returning `501` or are explicitly re-scoped with documented blockers
- route-level healthy and degraded semantics are frozen in tests and docs
- `reserve-risk` either remains held or moves only after an explicit source-of-truth decision justifies an independent local implementation

Current status:

- completed on 2026-04-02
- `/api/metrics/nupl` and `/api/metrics/cost-basis` are now DuckDB-backed research routes with explicit `404`/`503` semantics
- `reserve-risk` remains held at `501`

### Milestone M7: Research-to-Production Admission Review

Target window:

- 2026-05-19 to 2026-05-23

Includes:

- spec-049

Exit criteria:

- `nupl` and `cost-basis` each have an explicit go/no-go admission decision beyond `tier_3_research`
- field-level policy is frozen for any candidate consumer-facing subset
- required validation evidence is named for each route family
- `reserve-risk` is explicitly kept out of scope or moved only after a reopened source-of-truth decision

Current status:

- completed on 2026-04-02 as the post-`M6` governance track
- `nupl_surface` remains `tier_3_research`; only a reduced field subset may be reconsidered in a future contract revision
- `cost_basis_surface` remains `tier_3_research`; it is the strongest future candidate, but not admitted today
- `reserve-risk` remains out of scope pending an explicit `BRK` vs local source-of-truth reopening

## 8. Dependency Order

Recommended sequencing:

1. spec-044
2. spec-045
3. spec-048
4. spec-046 Wave 1
5. spec-047
6. spec-046 Wave 2+
7. spec-049

Reason:

- contract and provenance must exist before promotion decisions are meaningful
- hardening must happen before expanding the admitted surface
- whale unification should happen after contract rules exist, but it does not need to block Wave 1 calculator promotion

## 9. Estimated Effort

Planning estimate based on the new spec kits:

| Spec | Effort |
|------|--------|
| spec-044 | 2-3 days |
| spec-045 | 2.5-3 days |
| spec-048 | 2.5-5.5 days |
| spec-046 Wave 1 | 3-5 days |
| spec-047 | 4-7 days |
| spec-046 Wave 2+ | 2-4 days for Wave 2, then further waves |
| spec-049 | 1.5-3 days |

Compressed execution estimate:

- approximately 3-5 weeks of focused work, depending on how much can run in parallel and whether `PRO Risk` / `Puell Multiple` are hardened or demoted instead

## 10. Risks and Decision Points

### Risk A: Contract Drift

If spec-044 and spec-045 are not made authoritative early, the repo will keep adding routes without a stable consumer story.

### Risk B: Hardening vs Demotion Ambiguity

`PRO Risk` and `Puell Multiple` should not remain indefinitely in a limbo state where they are exposed but trusted only by convention.

### Risk C: History Materialization Cost

Some Wave 1 and Wave 2 metrics are blocked less by formula logic than by baseline/history persistence.

### Risk D: Whale Scope Expansion

Whale/entity work can sprawl quickly unless the first canonical event schema is kept intentionally narrow.

### Risk E: Research-Only Drift

Once a route is live, downstream consumers may treat it as implicitly admitted unless a separate admission gate exists. This is now the main risk for `nupl` and `cost-basis`.

## 11. Recommended Immediate Next Step

Start with the next evidence-producing slice, not a new admission change.

Concretely:

1. only reopen `nupl` admission if a future contract wants a reduced field subset and the validation evidence is refreshed with explicit operator sign-off
2. only reopen `cost-basis` admission after publishing reproducibility checks and a clear consumer-use statement
3. treat Wave 1 history materialization as the next substantive local engineering milestone; reopen `reserve-risk` only if the source-of-truth manifest is intentionally superseded

Do not promote any research-only route into a downstream consumer contract without updating the registry, provenance manifest, and consumer contract in the same change set.
