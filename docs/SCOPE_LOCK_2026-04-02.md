# Feature Service Scope Lock

Date: 2026-04-02

Status: Active scope guardrail for feature-service follow-up after `M7` and the metric source-of-truth freeze

Purpose:

- stop scope drift before new implementation work starts
- separate the canonical consumer contract from legacy and research surfaces
- prevent duplicate local productization of overlapping `BRK` metrics

Primary references:

- [docs/FEATURE_SERVICE_ROADMAP_2026-04-01.md](/media/sam/1TB/UTXOracle/docs/FEATURE_SERVICE_ROADMAP_2026-04-01.md)
- [docs/LIVE_STACK_ROLE_MATRIX.md](/media/sam/1TB/UTXOracle/docs/LIVE_STACK_ROLE_MATRIX.md)
- [docs/METRIC_SOURCE_OF_TRUTH_MANIFEST.md](/media/sam/1TB/UTXOracle/docs/METRIC_SOURCE_OF_TRUTH_MANIFEST.md)
- [docs/FEATURE_SERVICE_M7_DECISION_2026-04-02.md](/media/sam/1TB/UTXOracle/docs/FEATURE_SERVICE_M7_DECISION_2026-04-02.md)
- [docs/PRODUCTION_SURFACE_DISPOSITION_2026-04-02.md](/media/sam/1TB/UTXOracle/docs/PRODUCTION_SURFACE_DISPOSITION_2026-04-02.md)

## 1. Active Boundary

- `:8011` is the canonical live consumer contract
- `:8001` is a legacy, research, and transition surface; it is not the default expansion target
- `BRK` is the upstream feature engine for broad on-chain metric coverage
- `UTXOracle` should own only:
  - the normalized downstream consumer contract
  - repo-specific analytics not cleanly covered by upstreams
  - Wave 1 history/materialization work
  - whale and entity-aware forensic foundations

## 2. Immediate In-Scope Work

The active engineering slice is:

1. `spec-050` canonical `8011` promotion (**COMPLETE 2026-04-02**)
2. `spec-046` Phase 4 history/materialization debt (**COMPLETE 2026-04-02**)
3. validator and drift-check automation for `spec-044` and `spec-045`
4. whale/entity forensics only when it extends the canonical whale surface rather than reopening macro-metric duplication

Concrete next tasks:

- define persistent snapshot storage for `wallet-waves` baselines
- define writer/backfill workflow for `absorption-rates`
- add YAML/markdown consistency validation for the feature contract registry
- add drift validation for the feature provenance manifest
- keep route-family promotion decisions aligned with [docs/PRODUCTION_SURFACE_DISPOSITION_2026-04-02.md](/media/sam/1TB/UTXOracle/docs/PRODUCTION_SURFACE_DISPOSITION_2026-04-02.md)

## 3. Explicit No-Go Work

Do not start any of the following without a written scope reopening:

- local productization of `reserve-risk`
- new local admitted routes for overlapping macro metrics already acceptably exposed by `BRK`
- promotion of `nupl` or `cost-basis` beyond `tier_3_research`
- moving a route to `:8011` only because it exists on `:8001`
- treating the full `BRK` metric universe as an implementation backlog for `UTXOracle`

## 4. Decision Gate For New Work

Every proposed task must pass at least one of these tests:

1. it directly strengthens the canonical `:8011` consumer contract
2. it is repo-specific analytics that `BRK` does not expose or does not expose with the needed semantics
3. it extends the whale/entity forensic surface

If a task does not pass one of these tests, it is out of scope by default.

## 5. Reopen Conditions

The following areas may be reopened only with an explicit written decision:

### Overlapping macro metrics

Reopen only if:

- `BRK` does not expose the metric
- `BRK` semantics are inadequate for the intended use
- a deliberately different local methodology is approved

### `nupl` or `cost-basis` promotion

Reopen only if:

- a consumer-facing field subset is frozen
- the required evidence named in `M7` is published
- roadmap, registry, and contract artifacts are updated in the same change set

## 6. Practical Rule

The default answer to new metric work is:

- adopt from `BRK`
- keep local as research-only
- or do not expose it

The default answer is not:

- build another local production route
