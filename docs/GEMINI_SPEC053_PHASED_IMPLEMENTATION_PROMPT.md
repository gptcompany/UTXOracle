# Gemini Prompt: spec-053 Phased Implementation

Use this prompt to implement `spec-053` with extra caution. This spec is larger and semantically riskier than `spec-052`: identity, provenance, entity attribution, and flow-of-funds mistakes can silently poison downstream consumers. Advance in narrow review slices and stop at every semantic boundary.

## Role

You are implementing:

- [spec-053](/media/sam/1TB/UTXOracle/specs/053-btc-entity-and-flow-intelligence-plane/spec.md)

You are not implementing:

- trading strategy logic
- execution logic
- `spec-052` bundle/signal layer, except cross-spec documentation where explicitly required
- a `BRK` replacement for local entity/clustering semantics
- full AML/sanctions/institutional attribution

## Required Intake Before Any Work

Before touching files, read:

- [spec-053 spec.md](/media/sam/1TB/UTXOracle/specs/053-btc-entity-and-flow-intelligence-plane/spec.md)
- [spec-053 plan.md](/media/sam/1TB/UTXOracle/specs/053-btc-entity-and-flow-intelligence-plane/plan.md)
- [spec-053 tasks.md](/media/sam/1TB/UTXOracle/specs/053-btc-entity-and-flow-intelligence-plane/tasks.md)
- [spec-053 decisions.md](/media/sam/1TB/UTXOracle/specs/053-btc-entity-and-flow-intelligence-plane/decisions.md)
- [spec-053 design_registry.md](/media/sam/1TB/UTXOracle/specs/053-btc-entity-and-flow-intelligence-plane/design_registry.md)
- [spec-053 design_flow.md](/media/sam/1TB/UTXOracle/specs/053-btc-entity-and-flow-intelligence-plane/design_flow.md)
- [spec-053 design_materialization.md](/media/sam/1TB/UTXOracle/specs/053-btc-entity-and-flow-intelligence-plane/design_materialization.md)
- [cross-spec-sync.md](/media/sam/1TB/UTXOracle/specs/cross-spec-sync.md)
- [WHALE_ENTITY_FOUNDATION.md](/media/sam/1TB/UTXOracle/docs/WHALE_ENTITY_FOUNDATION.md)
- [ADDRESS_CLUSTERS_BRK_ADOPTION_CHECKLIST.md](/media/sam/1TB/UTXOracle/docs/ADDRESS_CLUSTERS_BRK_ADOPTION_CHECKLIST.md)
- [FEATURE_CONTRACT_REGISTRY.md](/media/sam/1TB/UTXOracle/docs/FEATURE_CONTRACT_REGISTRY.md)
- [FEATURE_DEPENDENCY_MATRIX.md](/media/sam/1TB/UTXOracle/docs/FEATURE_DEPENDENCY_MATRIX.md)
- [spec-047](/media/sam/1TB/UTXOracle/specs/047-whale-entity-surface-unification/spec.md)
- [spec-051](/media/sam/1TB/UTXOracle/specs/051-whale-entity-enrichment-operationalization/spec.md)

Then run:

```bash
git status --short
```

Do not include unrelated dirty files in your commit. If the worktree already contains unrelated changes, leave them alone and mention them in the final output.

## Non-Negotiable Boundaries

- Preserve `whale_event.v1` backward compatibility.
- Preserve current omission behavior: `entity = null` when enrichment is unavailable or ambiguous.
- Do not make deep entity success a hard dependency for base whale events.
- Do not overload `/api/whale` with deep entity semantics.
- Do not collapse `cluster_id` and `entity_id` back into the same concept.
- Do not add labels without provenance.
- Do not expose a single opaque confidence score as registry-grade evidence.
- Do not silently classify internal reshuffles as directional external flow.
- Do not assume `BRK` can replace local entity/clustering semantics unless the address-clusters adoption checklist is explicitly satisfied.
- Do not implement `/api/entities/search` or `/api/entities/top-movers` unless a later slice explicitly admits them with frozen payloads and serving semantics.
- Do not project into `btc_entity.v1` or `btc_flow.v2` unless this spec reaches the explicit projection decision slice.
- Treat `cluster:{cluster_id}` as a read-only whale-compatibility alias only; new entity APIs must normalize to canonical `btc:entity:*` identifiers.
- Do not treat a target `:8011` host decision as contract admission by itself; `/api/entities/*` is not an admitted supported surface until route families are frozen and governance artifacts are updated.

## Conservative Implementation Rules

- Prefer design freeze and RED tests before implementation.
- Prefer additive schemas and additive response fields over mutating existing whale contract fields.
- Favor `unknown`, `ambiguous`, `degraded`, or omission over false certainty.
- If provenance is missing, do not invent it.
- If confidence components are unavailable, surface which components participated rather than fabricating completeness.
- `confidence_overall` is first-slice `min(...)`, not a product and not a weighted score.
- If historical movement data is partial, expose `partial_materialization` or equivalent degraded state.
- If a live/QuestDB integration check cannot run locally, state the exact missing prerequisite.

## Decision Discipline

Any `Freeze`, `Decide`, or `Record` task must update:

- [spec-053 decisions.md](/media/sam/1TB/UTXOracle/specs/053-btc-entity-and-flow-intelligence-plane/decisions.md)

Rules:

- fill `Decision` only when final for the slice
- fill `Source Ref` with the spec section, commit, or implementation file that made it binding
- if a task affects a cross-spec coupling, update [cross-spec-sync.md](/media/sam/1TB/UTXOracle/specs/cross-spec-sync.md)
- implementation tasks must read from `decisions.md`, not from chat memory

## Commit and Review Policy

Use checkpoint commits, not one commit per task and not one omnibus commit.

Allowed pattern:

- one coherent commit per review slice
- up to three commits inside a slice only when naturally separated into design/test/implementation
- every commit must be reviewable and leave the repo coherent
- each commit must include the minimal tests/docs relevant to its delta
- after a review-stop checkpoint, stop and report; do not continue automatically

Forbidden pattern:

- `misc fixes`
- unrelated cleanup
- broad refactors
- opportunistic route expansion
- implementation before identity/provenance/flow semantics are frozen
- changing `spec-052` runtime behavior while implementing this spec
- including pre-existing unrelated worktree changes

## Resume Rule

When restarting from this prompt:

1. read the required intake files again
2. inspect `tasks.md` for the first incomplete task in the next unfinished review slice
3. inspect `decisions.md` for unresolved binding decisions from prior slices
4. inspect `cross-spec-sync.md` for unresolved coupling rows
5. inspect recent commits
6. continue only the next unfinished review slice

Do not repeat completed slices unless tests show a concrete regression.

## Review Slices

### Slice 1: Identity, Vocabulary, and Boundary Freeze

Target tasks:

- `T001`-`T005`

Scope:

- freeze the problem boundary
- freeze base vocabulary
- decide canonical `entity_id` format, generation strategy, and namespace vocabulary
- decide API namespace direction at design level
- record baseline heuristics already implemented and what must not be reinvented

Primary outputs:

- updated `spec-053/decisions.md`
- minimal spec/doc refinements only if needed
- no storage schema implementation
- no API implementation

Review stop:

- stop after a commit that freezes `T001`-`T005`
- review is required because all later registry/API work inherits identity semantics

Recommended commit title:

```text
docs: freeze spec-053 identity boundary
```

Output required:

```text
Phase slice completed: 1
Tasks covered:
Commit(s):
Decision rows updated:
Cross-spec sync rows updated:
Tests/checks run:
Residual risks:
Ready for review: yes
```

### Slice 2: Registry, Provenance, and Confidence Design

Target tasks:

- `T006`-`T015`

Scope:

- design `entity_registry`
- design `cluster_entity_map`
- design `entity_labels`
- design `entity_label_provenance`
- decide local-authoritative vs QuestDB artifacts at design level
- freeze registry/label status vocabulary
- freeze confidence components
- freeze provenance vocabulary
- design `confidence_overall` update/composition behavior
- design downgrade behavior when evidence becomes ambiguous or stale

Required discipline:

- no labels without provenance
- `confidence_overall` must remain conservative
- keep `entity_kind` classification separate from identity

Primary outputs:

- updated `spec-053/decisions.md`
- schema/design docs or migration design if necessary
- no writer/backfill implementation yet unless explicitly scoped as design-only scaffolding

Review stop:

- stop after registry/provenance/confidence design is committed
- review is required before mapping pipeline work

Recommended commit title:

```text
docs: design spec-053 registry provenance model
```

Output required:

```text
Phase slice completed: 2
Tasks covered:
Commit(s):
Decision rows updated:
Registry artifacts defined:
Confidence/provenance rules:
Tests/checks run:
Residual risks:
Ready for review: yes
```

### Slice 3: Mapping Pipeline and Flow Model

Target tasks:

- `T016`-`T027`

Scope:

- define how existing `address_clusters` rows become registry-grade cluster records
- define cluster-to-entity mapping generation or curation
- define how exchange labels and known entity hints feed the registry
- define curated override representation
- define reconciliation rules for disagreement
- design `entity_movement_events`
- design `entity_transfer_edges`
- design `entity_flows_daily`
- design `entity_balance_snapshots_daily`
- design `entity_counterparty_edges_daily`
- freeze movement classification vocabulary
- define internal reshuffle vs external directional flow semantics

Required discipline:

- do not rewrite existing clustering
- do not conflate event-centric movement records with relationship-centric transfer edges
- do not treat ambiguous or internal movement as external directional flow
- keep local `address_clusters` ownership unless BRK adoption checklist is explicitly satisfied

Primary outputs:

- updated `spec-053/decisions.md`
- mapping/flow design notes or schema design artifacts
- no serving API routes yet

Review stop:

- stop after mapping and flow model design is committed
- review is required before materialization/storage implementation

Recommended commit title:

```text
docs: define spec-053 mapping and flow model
```

Output required:

```text
Phase slice completed: 3
Tasks covered:
Commit(s):
Decision rows updated:
Flow artifacts defined:
Internal-vs-external rule:
Tests/checks run:
Residual risks:
Ready for review: yes
```

### Slice 4A: Materialization and Security Decisions

Target tasks:

- `T028`-`T033`

Scope:

- decide which artifacts must be materialized into QuestDB
- define writer/backfill jobs for registry and flow artifacts
- define freshness targets
- define stale/degraded/ambiguous behavior
- decide whether any first slice remains research-only on `:8001`
- record security posture for entity and flow APIs

Required discipline:

- no schema implementation in this slice unless a tiny design scaffold is unavoidable
- security posture must be explicit, not inherited by omission
- source-of-truth split must be explicit: local authoritative vs QuestDB serving copy

Review stop:

- stop after materialization/security decisions are committed
- review is required before storage/writer implementation

Recommended commit title:

```text
docs: freeze spec-053 serving and security decisions
```

Output required:

```text
Phase slice completed: 4A
Tasks covered:
Commit(s):
Decision rows updated:
Materialization decision:
Security posture:
Tests/checks run:
Residual risks:
Ready for review: yes
```

### Slice 4B: Storage, Writers, and Materialization Implementation

Target tasks:

- `T034`-`T038`

Scope:

- implement local authoritative storage for:
  - `entity_registry`
  - `cluster_entity_map`
  - `entity_labels`
  - `entity_label_provenance`
- implement registry writer/backfill from existing `address_clusters` and curated entity hints
- implement movement artifacts:
  - `entity_movement_events`
  - `entity_transfer_edges`
  - `entity_flows_daily`
  - `entity_balance_snapshots_daily`
  - `entity_counterparty_edges_daily`
- materialize serving-grade artifacts into QuestDB with freshness metadata
- implement reconciliation/update logic when mapping evidence or labels change

Required discipline:

- add tests for schema creation, idempotent backfill, provenance preservation, and degraded/ambiguous cases
- do not destroy or reinterpret existing `address_clusters`
- do not require entity registry success for existing whale routes
- ensure backfills are safe to rerun

Likely file areas:

- `scripts/clustering/address_clustering.py`
- `scripts/bootstrap/sync_clusters_to_questdb.py`
- `api/questdb_repository.py`
- new or existing clustering/entity scripts
- tests for entity registry/materialization/backfill

Review stop:

- stop after storage/writer/materialization implementation and tests are committed
- review is required before API surface work

Recommended commit title:

```text
feat: add entity registry materialization path
```

Output required:

```text
Phase slice completed: 4B
Tasks covered:
Commit(s):
Storage artifacts implemented:
Writers/backfills implemented:
Tests/checks run:
Residual risks:
Ready for review: yes
```

### Slice 5A: API Contract and RED Tests

Target tasks:

- `T039`-`T050`

Scope:

- freeze first route family for entity metadata lookup
- freeze first route family for entity history
- freeze first route family for movement and flow queries
- define pagination/filtering/time-window semantics
- define omission/degraded behavior for partially resolved counterparties
- define compatibility behavior for the canonical whale surface
- freeze minimum response shapes for metadata/history/flow routes
- write RED tests for metadata lookup routes
- write RED tests for history and movement/flow query routes
- write RED tests for internal-reshuffle vs external-flow classification edge cases

Required discipline:

- RED tests before route implementation
- no `/api/entities/search` or `/api/entities/top-movers` unless explicitly admitted later
- tests must cover `not_found`, `ambiguous`, `stale`, `degraded`, and `partial_materialization`
- tests must prove current whale omission semantics are not broken

Review stop:

- stop after API contract and RED tests are committed
- review is required before route implementation

Recommended commit title:

```text
test: add red tests for entity flow APIs
```

Output required:

```text
Phase slice completed: 5A
Tasks covered:
Commit(s):
Decision rows updated:
Route families frozen:
Expected RED tests:
Residual risks:
Ready for review: yes
```

### Slice 5B: API Implementation

Target tasks:

- `T051`-`T053`

Scope:

- implement entity metadata lookup routes
- implement entity history routes
- implement movement and flow query routes

Required discipline:

- make RED tests from Slice 5A pass GREEN
- preserve explicit degraded/error vocabulary
- preserve pagination and ordering semantics
- query serving-grade materialized artifacts; do not recompute expensive graph logic per request unless the serving decision explicitly allowed it

Likely file areas:

- `api/main.py`
- `api/routes/*`
- `api/models/*`
- `api/questdb_repository.py`
- tests introduced in Slice 5A

Review stop:

- stop after route implementation and GREEN tests are committed

Recommended commit title:

```text
feat: expose entity flow API surface
```

Output required:

```text
Phase slice completed: 5B
Tasks covered:
Commit(s):
Routes implemented:
Tests/checks run:
Residual risks:
Ready for review: yes
```

### Slice 6A: Whale and Future Bundle Integration Decisions

Target tasks:

- `T054`-`T057`

Scope:

- define how richer registry-backed `entity_id` values appear in whale enrichment without breaking `whale_event.v1`
- define whether and when this spec should project into a future `btc_entity.v1` bundle
- define whether `btc_flow.v2` should later reference the entity flow plane
- keep existing whale omission and ambiguity guarantees intact while adding richer entity resolution

Required discipline:

- this is a design/decision slice, not implementation
- update [cross-spec-sync.md](/media/sam/1TB/UTXOracle/specs/cross-spec-sync.md) if projections or compatibility rules are decided
- do not change the current whale event response yet

Review stop:

- stop after whale/future-bundle integration decisions are committed
- review is required before touching whale runtime code

Recommended commit title:

```text
docs: define entity whale integration boundary
```

Output required:

```text
Phase slice completed: 6A
Tasks covered:
Commit(s):
Cross-spec sync rows updated:
Whale compatibility decision:
Future bundle projection decision:
Residual risks:
Ready for review: yes
```

### Slice 6B: Whale Enrichment Upgrade

Target tasks:

- `T058`

Scope:

- implement whale surface enrichment upgrade using registry-backed entity objects without breaking `whale_event.v1`

Required discipline:

- additive only
- no deep entity hard dependency for base whale events
- `entity = null` remains valid when unavailable or ambiguous
- preserve current labels/fields unless explicitly superseded by compatibility decisions
- add regression tests for old consumers and enriched consumers

Likely file areas:

- `api/mempool_whale_endpoints.py`
- `api/questdb_repository.py`
- `docs/WHALE_ENTITY_FOUNDATION.md`
- tests for whale event compatibility/enrichment

Review stop:

- stop after whale enrichment upgrade and regression tests are committed

Recommended commit title:

```text
feat: add registry-backed whale enrichment
```

Output required:

```text
Phase slice completed: 6B
Tasks covered:
Commit(s):
Whale fields changed:
Compatibility tests run:
Residual risks:
Ready for review: yes
```

### Slice 7: Verification and Governance

Target tasks:

- `T059`-`T064`

Scope:

- verify RED tests from `T048`-`T050` now pass GREEN
- add contract tests for entity identity and provenance serialization
- add tests for ambiguous and unavailable attribution cases
- update feature contract registry if any new route family is admitted
- update provenance manifest for new registry and flow artifacts
- update address-clusters adoption checklist if any BRK-based entity alternative is proposed

Required discipline:

- docs must describe implemented behavior, not planned behavior
- if no new route family is admitted, say so and avoid fake registry updates
- do not update BRK adoption checklist unless a BRK-based entity alternative was actually proposed
- if live/QuestDB checks are not runnable, record exact missing prerequisites

Review stop:

- stop after final verification/governance commit

Recommended commit title:

```text
docs: align entity flow governance artifacts
```

Output required:

```text
Phase slice completed: 7
Tasks covered:
Commit(s):
Docs updated:
Tests/checks run:
Unrun checks and reason:
Residual risks:
Ready for review: yes
```

## Optional Hard Stop Rules

Stop immediately and report instead of continuing if:

- a needed identity decision is missing from `decisions.md`
- a route implementation would require changing `whale_event.v1`
- a data source for labels lacks provenance
- QuestDB schema/materialization would be destructive or non-idempotent
- `BRK` appears to expose possible entity/clustering data but equivalence is not already proven in the adoption checklist
- API behavior would expose false certainty for ambiguous counterparties

## Final Output Contract for Every Run

At the end of any run, print exactly this structure:

```text
Spec: 053
Slice completed:
Tasks completed:
Commits:
Files changed:
Decision rows updated:
Cross-spec sync rows updated:
Tests/checks run:
Tests/checks not run:
Residual risks:
Unrelated worktree changes left untouched:
Ready for review: yes/no
Next recommended slice:
```

If no commit was created, say so explicitly and explain why.
