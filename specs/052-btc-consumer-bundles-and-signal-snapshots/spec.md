# spec-052: BTC Consumer Bundles and Signal Snapshots

> **Status**: DRAFT
> **Priority**: HIGH
> **Effort**: Large
> **Created**: 2026-04-06

## Problem Statement

The repository now has a credible production consumer surface on `:8011`, but it is still fragmented across route families and backend cadences rather than frozen as a small set of versioned machine-consumable bundles.

Current strengths already present:

1. `:8011 /api/v1/live/*` is the canonical live consumer surface
2. `:8011 /api/prices/*` and `:8011 /api/metrics/latest` are already promoted and runtime verified
3. `:8011 /api/whale/{transactions,summary,transaction/{txid}}` is canonical and entity-ready
4. `:8011 /api/metrics/address-cohorts`, `/wallet-waves`, and `/absorption-rates` are now QuestDB-backed and materialized

Current gaps that still block a clean "automatic pipe" consumption model:

1. the production-ready surfaces are still spread across multiple families rather than frozen as a few canonical BTC bundles
2. there is no versioned `signal snapshot` surface separated cleanly from raw feature surfaces
3. there is no monotonic `sequence_id` or equivalent cross-bundle identifier suitable for strict replay and consumer deduplication
4. history/replay semantics are inconsistent across families
5. `cost_basis` is analytically strong and repo-native, but still lives as a DuckDB-backed `tier_3_research` route on `:8001`
6. overlapping macro metrics (`NUPL`, `SOPR`, `liveliness`, `reserve_risk`, `realized_price_usd`) still need an explicit normalized bundle policy centered on `BRK`
7. `metrics_latest` is intentionally narrow today and is not itself a full feature plane
8. `RBN` remains useful for validation, but it should not leak into the production consumer path

This spec turns the current surface inventory into a deliberate BTC feature service that is production-ready for automated downstream consumption.

## Goals

1. freeze a small set of versioned BTC feature bundles for downstream consumption
2. promote `cost_basis` into the production-consumable service profile
3. define one versioned `btc_signal_snapshot.v1` surface derived only from admitted bundle fields
4. adopt `BRK` as the default macro upstream for overlapping shared metric semantics
5. make history/replay, freshness, stale, and degraded semantics uniform enough for automation
6. introduce a strong monotonic identifier (`sequence_id` or equivalent) across the new bundle and signal surfaces

## Non-Goals

- mirroring the full `BRK` metric universe into `UTXOracle`
- replacing `BRK` as the upstream source for overlapping shared macro metrics
- implementing exchange execution or strategy logic
- solving the full entity intelligence and flow-of-funds problem in this spec
- keeping `RBN` in the production consumer path
- admitting every `:8001` research route into the canonical consumer contract

## Dependencies

- [specs/040-utxoracle-live-service/spec.md](/media/sam/1TB/UTXOracle/specs/040-utxoracle-live-service/spec.md)
- [specs/041-questdb-operational-convergence/spec.md](/media/sam/1TB/UTXOracle/specs/041-questdb-operational-convergence/spec.md)
- [specs/043-nautilus-live-trading-integration/spec.md](/media/sam/1TB/UTXOracle/specs/043-nautilus-live-trading-integration/spec.md)
- [specs/044-feature-service-contract-registry/spec.md](/media/sam/1TB/UTXOracle/specs/044-feature-service-contract-registry/spec.md)
- [specs/045-feature-dependency-provenance-manifest/spec.md](/media/sam/1TB/UTXOracle/specs/045-feature-dependency-provenance-manifest/spec.md)
- [specs/046-calculator-surface-productization/spec.md](/media/sam/1TB/UTXOracle/specs/046-calculator-surface-productization/spec.md)
- [specs/047-whale-entity-surface-unification/spec.md](/media/sam/1TB/UTXOracle/specs/047-whale-entity-surface-unification/spec.md)
- [specs/050-canonical-8011-promotion/spec.md](/media/sam/1TB/UTXOracle/specs/050-canonical-8011-promotion/spec.md)
- [specs/051-whale-entity-enrichment-operationalization/spec.md](/media/sam/1TB/UTXOracle/specs/051-whale-entity-enrichment-operationalization/spec.md)

Primary architectural references:

- [docs/PRODUCTION_CONSUMER_SERVICE_PROFILE_2026-04-05.md](/media/sam/1TB/UTXOracle/docs/PRODUCTION_CONSUMER_SERVICE_PROFILE_2026-04-05.md)
- [docs/LIVE_STACK_ROLE_MATRIX.md](/media/sam/1TB/UTXOracle/docs/LIVE_STACK_ROLE_MATRIX.md)
- [docs/METRIC_SOURCE_OF_TRUTH_MANIFEST.md](/media/sam/1TB/UTXOracle/docs/METRIC_SOURCE_OF_TRUTH_MANIFEST.md)
- [docs/FEATURE_CONTRACT_REGISTRY.md](/media/sam/1TB/UTXOracle/docs/FEATURE_CONTRACT_REGISTRY.md)
- [docs/FEATURE_DEPENDENCY_MATRIX.md](/media/sam/1TB/UTXOracle/docs/FEATURE_DEPENDENCY_MATRIX.md)

Implementation entry points likely to be touched:

- [api/routes/questdb.py](/media/sam/1TB/UTXOracle/api/routes/questdb.py)
- [api/models/questdb.py](/media/sam/1TB/UTXOracle/api/models/questdb.py)
- [api/main.py](/media/sam/1TB/UTXOracle/api/main.py)
- [api/questdb_repository.py](/media/sam/1TB/UTXOracle/api/questdb_repository.py)
- [scripts/metrics/materialize_wave1.py](/media/sam/1TB/UTXOracle/scripts/metrics/materialize_wave1.py)
- [scripts/live/source_clients.py](/media/sam/1TB/UTXOracle/scripts/live/source_clients.py)
- [scripts/live/models.py](/media/sam/1TB/UTXOracle/scripts/live/models.py)
- [scripts/metrics/cost_basis.py](/media/sam/1TB/UTXOracle/scripts/metrics/cost_basis.py)
- [scripts/models/metrics_models.py](/media/sam/1TB/UTXOracle/scripts/models/metrics_models.py)
- [docs/contracts/feature_contract_registry.yaml](/media/sam/1TB/UTXOracle/docs/contracts/feature_contract_registry.yaml)
- [docs/contracts/metric_source_of_truth_manifest.yaml](/media/sam/1TB/UTXOracle/docs/contracts/metric_source_of_truth_manifest.yaml)

## Current Baseline

### Production-ready surfaces already present

The service profile already recognizes these production-consumable families:

- `:8011 /api/v1/live/*`
- `:8011 /api/v1/charts/*`
- `:8011 /api/prices/*`
- `:8011 /api/metrics/latest`
- `:8011 /api/whale/{transactions,summary,transaction/{txid}}`
- `:8011 /api/metrics/address-cohorts`
- `:8011 /api/metrics/wallet-waves`
- `:8011 /api/metrics/absorption-rates`

### Important baseline caveats

- `metrics_latest_surface` is intentionally compact today and currently includes only `monte_carlo`, `active_addresses`, and `tx_volume`
- the live worker currently fetches only a curated BRK subset:
  - `realized_price_usd`
  - `liveliness`
  - `reserve_risk`
- `cost_basis_surface` is still a DuckDB-backed `tier_3_research` route on `:8001`
- local `NUPL` remains research-only and explicitly estimated in part; future shared/admitted consumption is `BRK`-first
- `RBN` is validation-only and quota-bound
- `wallet-waves/history` is still not part of the admitted production consumer surface

### Source-of-truth baseline

Current metric ownership that this spec must preserve unless explicitly superseded:

- `utxoracle_price`: local canonical
- `cost_basis`: local canonical
- `NUPL`: `BRK`-first for future shared/admitted use
- `SOPR`: `BRK`-first for future shared/admitted use
- `liveliness`: `BRK`-first for future shared/admitted use
- `reserve_risk`: `BRK`-first for future shared/admitted use

### Boundary decisions already frozen before implementation

These decisions are already considered settled input to this spec:

- `metrics_latest_surface` remains intentionally narrow; it is not to be expanded into a generic all-metrics mirror
- `btc_macro.v1` must remain a curated `BRK` subset, not a proxy of the full `BRK` universe
- `cost_basis` remains `local_canonical` unless an exact upstream equivalent is named, verified, and contractually frozen
- local `NUPL` remains research-only even if `btc_macro.v1` later carries a production/shared `BRK`-normalized `NUPL`
- `RBN` remains outside the production consumer path
- `btc_flow.v1` is allowed to start with whale and absorption context without pretending that a full entity flow plane already exists
- this spec does not solve canonical `entity_id`, label provenance, or registry-grade attribution; those belong to `spec-053`

## Design

### 1. Bundle Strategy

This spec defines exactly four versioned BTC feature bundles:

- `btc_core_live.v1`
- `btc_flow.v1`
- `btc_macro.v1`
- `btc_cohort.v1`

These are not "all features in one blob." They are intentionally separate so downstream consumers can choose a narrow contract slice.

### 2. Bundle Namespace

Recommended new route families:

- `GET /api/features/btc/core/latest`
- `GET /api/features/btc/core/history`
- `GET /api/features/btc/flow/latest`
- `GET /api/features/btc/flow/history`
- `GET /api/features/btc/macro/latest`
- `GET /api/features/btc/macro/history`
- `GET /api/features/btc/cohort/latest`
- `GET /api/features/btc/cohort/history`
- `GET /api/signals/btc/latest`
- `GET /api/signals/btc/history`

The existing route families remain valid and continue to exist. These new routes are a consumer-oriented bundle plane, not a replacement for every underlying family.

### 3. `btc_core_live.v1`

Purpose:

- fast, replayable live market-state bundle for automatic consumers

Composition:

- `live_snapshot_surface`
- `metrics_latest_surface`

Payload direction:

- top-level bundle metadata:
  - `schema_version`
  - `bundle_id`
  - `sequence_id`
  - `produced_at`
  - `bundle_status`
  - `degraded_reasons`
- nested `live_snapshot` block:
  - `timestamp`
  - `block_height`
  - `utxoracle_price`
  - `utxoracle_confidence`
  - `mempool_exchange_price`
  - `hyperliquid_oracle_price`
  - `hyperliquid_mark_price`
  - `comparison.utxo_vs_mempool_bps`
  - `comparison.utxo_vs_hl_oracle_bps`
  - `comparison.utxo_vs_hl_mark_bps`
  - `source_health`
  - `source_timestamps`
- nested `metrics_latest` block:
  - `timestamp`
  - `monte_carlo.*`
  - `active_addresses.*`
  - `tx_volume.*`

Important rule:

- `btc_core_live.v1` MUST preserve sub-component timestamps rather than flattening different producer cadences into one fake atomic timestamp

### 4. `btc_flow.v1`

Purpose:

- standardized BTC flow bundle for event-driven and conviction-aware consumers

Initial admitted source families:

- canonical whale query surface
- `absorption-rates`
- optional later inclusion of `exchange-netflow` only after serving-grade materialization or explicit transition semantics are frozen

Initial payload direction:

- top-level bundle metadata:
  - `schema_version`
  - `bundle_id`
  - `sequence_id`
  - `produced_at`
  - `bundle_status`
  - `degraded_reasons`
- nested `whale_summary` block:
  - `total_transactions`
  - `total_btc_volume`
  - `avg_urgency_score`
  - `high_urgency_count`
  - `rbf_enabled_count`
  - `entity_enrichment_mode`
- nested `recent_whale_window` block:
  - latest-window aggregate fields derived from canonical whale events
  - count of enriched vs non-enriched events
  - last_event_timestamp
- nested `absorption_rates` block:
  - `window_days`
  - `dominant_absorber`
  - `retail_absorption`
  - `institutional_absorption`
  - `confidence`
  - `has_historical_data`

Explicit non-goal for `v1`:

- do not silently mix in `exchange-netflow`, `binary-cdd`, `net-realized-pnl`, `pl-ratio`, or `NVT` unless their serving semantics are frozen for bundle use

### 5. `btc_macro.v1`

Purpose:

- normalized macro bundle for shared on-chain metric consumption

Source-of-truth rule:

- this bundle is `BRK`-first for overlapping shared macro metrics
- local research routes are not the default source for this bundle

Initial target metric set:

- `realized_price_usd`
- `liveliness`
- `reserve_risk`
- `NUPL`
- `SOPR`

Current implementation note:

- the live worker currently curates only:
  - `realized_price_usd`
  - `liveliness`
  - `reserve_risk`
- this spec extends the curated BRK subset deliberately rather than exposing the full BRK fanout

Payload direction:

- top-level bundle metadata:
  - `schema_version`
  - `bundle_id`
  - `sequence_id`
  - `produced_at`
  - `bundle_status`
  - `degraded_reasons`
- nested `macro_metrics` block:
  - `realized_price_usd`
  - `liveliness`
  - `reserve_risk`
  - `nupl`
  - `sopr`
- nested `source_metadata` block:
  - `source="BRK"`
  - `source_timestamp`
  - `source_health`
  - `missing_metrics`

Hard rule:

- the bundle may omit or null individual metrics when BRK is partially degraded, but it must declare that degradation explicitly

### 6. `btc_cohort.v1`

Purpose:

- versioned current-state cohort and holder-structure bundle

Composition:

- `address-cohorts`
- `wallet-waves`
- `absorption-rates`
- promoted `cost_basis`

Important policy:

- `cost_basis` remains locally owned unless an exact BRK equivalent is named, verified, and contractually frozen
- a BRK compare path is allowed for diagnostics and operator confidence, but it does not change ownership by itself

Payload direction:

- top-level bundle metadata:
  - `schema_version`
  - `bundle_id`
  - `sequence_id`
  - `produced_at`
  - `bundle_status`
  - `degraded_reasons`
- nested `address_cohorts` block:
  - entire current `AddressCohortsResponse` shape
- nested `wallet_waves` block:
  - entire current `WalletWavesResponse` shape
- nested `absorption_rates` block:
  - entire current `AbsorptionRatesResponse` shape
- nested `cost_basis` block:
  - `sth_cost_basis`
  - `lth_cost_basis`
  - `total_cost_basis`
  - `sth_mvrv`
  - `lth_mvrv`
  - `current_price_usd`
  - `block_height`
  - `timestamp`
  - `confidence`

Optional fields that may remain outside the admitted bundle if they are not needed:

- `sth_supply_btc`
- `lth_supply_btc`

### 7. Cost Basis Promotion Rule

`cost_basis` is the next local promotion target, but it must not remain a request-time-only DuckDB route if it becomes part of the production-ready consumer service.

This spec therefore requires:

1. define a stable admitted field subset for `cost_basis`
2. publish reproducibility and operator acceptance evidence
3. define a serving-grade read path for the promoted slice
4. decide whether serving remains DuckDB-backed with explicit caveats or moves to QuestDB materialization

Strong recommendation:

- materialize the admitted `cost_basis` slice into QuestDB and serve it on `:8011`

### 8. Cost Basis vs BRK Comparison Policy

This spec allows and encourages comparison against BRK where an equivalent metric appears to exist.

However:

- comparison is not ownership transfer
- if BRK does not expose an exact equivalent, local ownership stands
- if BRK exposes only conceptually similar cohort analytics, local `cost_basis` remains canonical until semantic equivalence is explicitly frozen

Required decision artifact:

- a short compare note or validation artifact naming whether BRK has:
  - no equivalent
  - partial overlap only
  - exact equivalent candidate

### 9. `sequence_id`

The production consumer bundles and the signal snapshot surface MUST have a monotonic identifier.

Preferred model:

- `sequence_id` is generated by the production bundle writer
- `sequence_id` is monotonically increasing within each bundle family
- `btc_signal_snapshot.v1` also records the referenced bundle sequence IDs used for the calculation

Important compatibility note:

- the raw live snapshot contract still does not expose its own upstream `sequence_id`
- this spec therefore treats bundle-level `sequence_id` as a serving-plane identifier generated by the new bundle writer
- later addition of raw upstream `sequence_id` to the live snapshot remains desirable, but it is not a prerequisite for `btc_*_v1` bundles

Stretch goal:

- one cross-bundle generation ID shared by all bundle writes that belong to the same service cycle

### 10. History and Replay Policy

Every new bundle route MUST support a stable history/replay path.

Minimum rule set:

- `latest` returns the newest valid row
- `history` returns rows ordered oldest-to-newest by `sequence_id` then `produced_at`
- every row carries:
  - bundle schema version
  - bundle-level status
  - per-source freshness or source timestamp metadata

Cadence expectations:

- `btc_core_live.v1`: live cadence
- `btc_flow.v1`: mixed cadence; emitted when whale/flow aggregates update
- `btc_macro.v1`: bounded periodic snapshot from BRK
- `btc_cohort.v1`: daily or slower materialization cadence

### 11. Uniform Failure Vocabulary

Every bundle and signal route MUST explicitly support:

- `empty`
- `stale`
- `degraded`
- `misconfigured`

The route contract must not force downstream consumers to infer these states from random missing fields.

### 12. `btc_signal_snapshot.v1`

Purpose:

- deliver one deterministic, versioned signal layer derived only from admitted bundle inputs

This is not a trading strategy and must not encode position sizing or order routing.

Candidate payload:

- `schema_version`
- `sequence_id`
- `produced_at`
- `block_height`
- `service_status`
- `bias`
- `conviction`
- `regime_score`
- `flow_score`
- `valuation_score`
- `quality_score`
- `degraded_reasons`
- `input_refs`
  - `core_sequence_id`
  - `flow_sequence_id`
  - `macro_sequence_id`
  - `cohort_sequence_id`
- `component_details`
  - named component inputs and normalized sub-scores

Signal-layer rules:

1. formulas must be deterministic and documented
2. only admitted bundle fields may be used
3. missing or degraded upstream bundle state must affect `service_status` and `quality_score`
4. the signal snapshot must remain clearly separated from strategy logic

### 13. `RBN` Exclusion Rule

`RBN` is explicitly outside the production consumer path.

Implications:

- no `RBN` dependency in the bundle writers
- no `RBN` field in the feature bundles
- no `RBN` field in `btc_signal_snapshot.v1`
- validation against `RBN` may remain an operator or research workflow only

## Functional Requirements

### FR1: Versioned Bundle Plane

The repository MUST expose a versioned BTC bundle plane rather than forcing consumers to assemble the production feature contract route by route.

### FR2: Four Named Bundle Families

The first bundle plane MUST define exactly:

- `btc_core_live.v1`
- `btc_flow.v1`
- `btc_macro.v1`
- `btc_cohort.v1`

### FR3: Cost Basis Promotion

The first local expansion candidate beyond the current service profile MUST be `cost_basis`, not a broad reopening of local overlapping macro metrics.

### FR4: BRK-First Macro Policy

The macro bundle MUST treat `BRK` as the preferred source for overlapping shared macro metrics unless a different written decision supersedes the current manifest.

### FR5: No Full BRK Mirror

The implementation MUST NOT mirror or proxy the full `BRK` metric universe.

### FR6: Monotonic Identifier

Every bundle row and every signal snapshot row MUST carry a monotonic identifier suitable for replay and consumer deduplication.

### FR7: History Support

Every bundle and signal surface MUST have a history route or replay path with stable ordering semantics.

### FR8: Uniform Failure Semantics

Every bundle and signal surface MUST expose explicit `empty`, `stale`, `degraded`, and `misconfigured` semantics.

### FR9: Signal Separation

The repository MUST provide a versioned signal snapshot surface that is clearly separated from raw feature bundles.

### FR10: `RBN` Exclusion

The new bundle and signal plane MUST remain independent of `RBN`.

### FR11: Contract and Provenance Alignment

The final implementation MUST update:

- contract registry
- provenance manifest
- production service profile
- scope lock
- consumer contract docs

## Implementer Handoff

The intended order of attack is:

1. freeze the four bundle schemas and `btc_signal_snapshot.v1`
2. freeze `sequence_id` and history semantics before wiring any API route
3. promote `cost_basis` with a serving-grade path instead of leaving it request-time only
4. extend the curated `BRK` subset only to the exact macro fields admitted into `btc_macro.v1`
5. add bundle writers and history routes
6. add the signal writer only after bundle persistence exists
7. update registry/provenance/governance docs only after route and storage decisions are frozen

Implementation risks to watch explicitly:

- duplicating the full `BRK` metric universe instead of keeping a narrow admitted subset
- promoting `cost_basis` without freezing a small consumer field subset
- mixing research-only routes from `:8001` into bundle responses by convenience
- inventing strategy-specific logic inside `btc_signal_snapshot.v1`
- coupling bundle monotonicity to upstream raw live snapshot sequencing that does not yet exist

## Success Criteria

1. the repo exposes one explicit BTC bundle plane and one explicit BTC signal plane
2. `cost_basis` is no longer stranded as a research-only local route if it is needed by the production consumer service
3. overlapping macro metrics are normalized from `BRK` rather than duplicated locally by default
4. downstream consumers can replay rows in strict order using a monotonic identifier
5. the signal surface is deterministic, versioned, and does not require strategy code inside the service
6. `RBN` is fully absent from the production consumer path
7. docs, registry, provenance, and runtime all tell the same story
