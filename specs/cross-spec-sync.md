# Cross-Spec Sync: spec-052 + spec-053

This file tracks the binding couplings between:

- [spec-052](/media/sam/1TB/UTXOracle/specs/052-btc-consumer-bundles-and-signal-snapshots/spec.md)
- [spec-053](/media/sam/1TB/UTXOracle/specs/053-btc-entity-and-flow-intelligence-plane/spec.md)

Note: the execution-grade NT pack (`spec-054` through `spec-059`) uses [execution-grade-nt-cross-spec-sync.md](/media/sam/1TB/UTXOracle/specs/execution-grade-nt-cross-spec-sync.md).

Usage:

- keep one row per real coupling, not per discussion
- update `Resolution` only when both sides are aligned
- use `Locked In` to point to the commit, spec section, or implementation artifact that made the coupling concrete

| Coupling | Canonical Owner / Decision Home | spec-052 Touchpoint | spec-053 Touchpoint | Sync Rule | Resolution | Locked In |
|----------|----------------------------------|---------------------|---------------------|-----------|------------|-----------|
| `whale_event.v1` compatibility | current whale contract (`spec-047` / `spec-051`); compatibility rules enforced by `spec-053` | `btc_flow.v1` consumes whale context and must not imply richer entity guarantees than the canonical whale surface | richer registry-backed entity references are additive only; `whale_event.v1` must remain backward compatible | no `spec-053` change may make deep entity success a hard dependency for the base whale event or silently change the event contract used by `btc_flow.v1` |  |  |
| `absorption_rates` ownership | `spec-052` (`btc_cohort.v1` owns the canonical slice) | `btc_flow.v1` may include a convenience copy for flow-oriented consumers | entity/flow work must not fork or redefine the absorption semantics already owned by the bundle plane | there is one canonical materialized source; downstream copies are projections only, never independent computations |  |  |
| `btc_flow.v1` -> future `btc_flow.v2` projection | `spec-052` owns `btc_flow.v1`; `spec-053` may justify future projection only after entity plane matures | `btc_flow.v1` starts bounded: whale + absorption context without pretending to be a full entity flow plane | `spec-053` may later support `btc_flow.v2` using registry-backed entity flow artifacts | no backdoor expansion of `btc_flow.v1`; richer entity flow enters only through an explicit later version/projection decision |  |  |
| entity enrichment in whale surface | canonical whale surface today; `spec-053` owns deeper registry-backed enrichment path | `btc_flow.v1` may expose whale-derived `entity_enrichment_mode` and summary context | richer `entity_id` and registry objects may appear in whale enrichment if omission/ambiguity guarantees remain intact | `entity = null` remains the minimum compatibility baseline; richer entity resolution must stay additive and non-breaking |  |  |
| `BRK` macro policy boundary | `spec-052`, source-of-truth manifest, and related governance docs | `btc_macro.v1` is curated and `BRK`-first for overlapping shared macro metrics | entity/clustering semantics remain local unless the address-clusters adoption checklist is explicitly satisfied | `spec-053` must not import `BRK` macro ownership decisions or assume `BRK` can replace local entity/clustering semantics by analogy |  |  |
| security posture decision pattern | `Gate E` in both plans; each spec owns its final route exposure decision | bundle/signal routes on the consumer plane require an explicit security posture decision before exposure | entity/flow routes require the same explicit decision discipline before exposure | both specs must record an explicit security posture decision rather than inheriting host behavior by omission |  |  |
