# Tasks: UTXOracle Live Service (spec-040)

**Input**: Design documents from `/specs/040-utxoracle-live-service/`
**Prerequisites**: plan.md (required), spec.md (required)

**Tests**: TDD is mandatory for models, source clients, comparison logic, worker logic, and API endpoints.

**Organization**: Five user stories: source normalization, comparison engine, snapshot production, consumer API, and Docker deployment.

## Format: `[ID] [Markers] [Story] Description`

### Task Markers
- **[P]**: Can run in parallel
- **[E]**: Complex integration or algorithmic task
- **[Story]**: User story label such as `US1`, `US2`, `US3`, `US4`, `US5`

---

## Phase 1: Setup

**Purpose**: Verify runtime assumptions and prepare the implementation workspace.

- [x] T001 Verify current host endpoints for `electrs`, `mempool-api`, `BRK`, `hyperliquid-node /info`, and `hyperliquid-node metrics`, and capture them in docs or env config
- [x] T002 Verify the local Hyperliquid filtered path on `4TB-NVMe` and confirm `coin_to_oracle_px` and `coin_to_mark_px` are available for consumption
- [x] T003 Create `scripts/live/` package scaffold and import path tests

---

## Phase 2: Foundational Config and Models

**Purpose**: Define the contract and configuration that all other tasks depend on.

**Critical**: No worker or API code should be written before the normalized models and env-driven configuration exist.

- [x] T004 Add live service env settings to `api/config.py`
- [x] T005 Align legacy default ports in `scripts/config/mempool_config.py` with env-driven overrides
- [x] T006 [US1] Create `scripts/live/models.py` with `SourceHealth`, `LiveFeatureSet`, `LiveComparison`, and `LiveSnapshot`
- [x] T007 [US1] Write `tests/test_live_models.py` for schema validation and serialization
- [ ] T008 [US1] Run `uv run pytest tests/test_live_models.py -v` and confirm RED then GREEN workflow

**Checkpoint**: Configuration and contract are ready for integration work.

---

## Phase 3: User Story 1 - Source Normalization (Priority: P1)

**Goal**: Normalize electrs, mempool, BRK, and Hyperliquid into one local schema.

**Independent Test**:
- `uv run pytest tests/test_live_source_clients.py -v` passes
- each client returns normalized payload plus source health metadata

### Tests for User Story 1

- [x] T009 [US1] Write client tests for electrs tip and health behavior
- [x] T010 [US1] Write client tests for mempool price and failure handling
- [x] T011 [US1] Write client tests for curated BRK feature fetches
- [x] T012 [US1] Write client tests for Hyperliquid filtered oracle-update loading and optional `POST /info` parsing

### Implementation for User Story 1

- [x] T013 [US1] Create `scripts/live/source_clients.py`
- [x] T014 [E] [US1] Implement `ElectrsClient`
- [x] T015 [E] [US1] Implement `MempoolApiClient`
- [x] T016 [E] [US1] Implement `BrkClient`
- [x] T017 [US1] Implement `HyperliquidSnapshotClient` against `hyperliquid-node` filtered oracle updates and optional `POST /info` parsing
- [x] T018 [US1] Run `uv run pytest tests/test_live_source_clients.py -v`

**Checkpoint**: All upstreams can be queried through one normalized interface.

---

## Phase 4: User Story 2 - Comparison Engine (Priority: P1)

**Goal**: Compute live match or deviation fields against declared external references.

**Independent Test**:
- `uv run pytest tests/test_live_comparison.py -v` passes
- comparison engine returns correct basis-point deviations and handles missing sources cleanly

### Tests for User Story 2

- [x] T019 [US2] Write comparison test for UTXOracle vs mempool exchange price
- [x] T020 [US2] Write comparison test for UTXOracle vs Hyperliquid oracle price
- [x] T021 [US2] Write comparison test for UTXOracle vs Hyperliquid mark price
- [x] T022 [US2] Write comparison test for null or degraded upstream inputs

### Implementation for User Story 2

- [x] T023 [US2] Create `scripts/live/comparison.py`
- [x] T024 [US2] Implement basis-point calculation helpers
- [x] T025 [US2] Implement normalized `LiveComparison` assembly
- [x] T026 [US2] Run `uv run pytest tests/test_live_comparison.py -v`

**Checkpoint**: Comparison logic is explicit and reusable.

---

## Phase 5: User Story 3 - Live Snapshot Worker (Priority: P1)

**Goal**: Produce persisted live snapshots with source health and comparison fields.

**Independent Test**:
- `uv run pytest tests/test_live_worker.py -v` passes
- worker preserves last good snapshot during degraded source cycles

### Tests for User Story 3

- [x] T027 [US3] Write test for healthy worker cycle that writes one snapshot row
- [x] T028 [US3] Write test for block height change triggering block-bound refresh
- [x] T029 [US3] Write test for degraded upstream cycle retaining last good snapshot semantics
- [x] T030 [US3] Write test that snapshot rows include comparison fields and curated BRK features

### Implementation for User Story 3

- [x] T031 [US3] Create `scripts/live/storage.py` with DuckDB schema bootstrap and read helpers
- [x] T032 [US3] Create `scripts/live/worker.py` with polling loop and snapshot assembly
- [x] T033 [E] [US3] Implement block cadence refresh logic based on `electrs` tip
- [x] T034 [US3] Implement market cadence refresh logic for mempool and Hyperliquid inputs
- [x] T035 [US3] Implement degraded state behavior and last-good-snapshot handling
- [x] T036 [US3] Run `uv run pytest tests/test_live_worker.py -v`

**Checkpoint**: Live snapshot rows are produced locally and survive upstream issues.

---

## Phase 6: User Story 4 - Consumer API (Priority: P2)

**Goal**: Expose a stable live contract for Nautilus Trader and backtest engines.

**Independent Test**:
- `uv run pytest tests/test_live_api.py -v` passes
- `GET /api/v1/live/snapshot` and `GET /api/v1/live/comparison/latest` return valid payloads

### Tests for User Story 4

- [x] T037 [US4] Write API test for `GET /api/v1/live/snapshot`
- [x] T038 [US4] Write API test for `GET /api/v1/live/history`
- [x] T039 [US4] Write API test for `GET /api/v1/live/comparison/latest`
- [x] T040 [US4] Write API test for `GET /api/v1/live/ready`

### Implementation for User Story 4

- [x] T041 [US4] Extend `api/main.py` with live response models and live routes
- [x] T042 [US4] Wire live storage reads into API handlers
- [x] T043 [US4] Extend `GET /health` with live source summary when `LIVE_ENABLED=true`
- [x] T044 [US4] Add `GET /api/v1/live/ready` probe endpoint
- [x] T045 [US4] Run `uv run pytest tests/test_live_api.py -v`

**Checkpoint**: One consumer API endpoint family is available for live usage.

---

## Phase 7: User Story 5 - Docker Deployment (Priority: P2)

**Goal**: Package the live system as a Docker deployable service.

**Independent Test**:
- `docker compose -f docker-compose.live.yml config` is valid
- live worker and API start with env-driven endpoints

### Implementation for User Story 5

- [x] T046 [US5] Create `Dockerfile.live`
- [x] T047 [US5] Create `docker-compose.live.yml` with `utxoracle-live-worker` and `utxoracle-live-api`
- [x] T048 [US5] Update `utxoracle-api.service` or add a companion service unit for live API mode
- [x] T049 [US5] Document runtime env vars and volume mounts in `docs/ARCHITECTURE.md`
- [x] T050 [P] [US5] Run compose validation and startup smoke checks

**Checkpoint**: Live service can be started and monitored as a host-level Docker deployment.

---

## Phase 8: Alignment and Cleanup

**Purpose**: Remove known integration drift that would confuse operators and future work.

- [x] T051 [P] Update `scripts/compare_brk_utxoracle.py` to default to env-driven `BRK_BASE_URL`
- [x] T052 [P] Update `scripts/validate_brk_integration.py` to default to env-driven `BRK_BASE_URL`
- [x] T053 [P] Update any live-critical `electrs` references that still default to `localhost:3001`
- [x] T054 [P] Add operational notes for port alignment and current host topology
- [x] T055 Run targeted regression tests for touched modules

---

## Deferred Follow-up

These are intentionally not part of the MVP service implementation:
- BRK visual validation dashboard
- chart parity workflow against external providers
- broader BRK metric exploration UI

---

## Dependencies and Execution Order

### Phase Dependencies

- Setup must complete before config and models
- Foundational config and models block all user stories
- User Story 1 blocks User Story 2 and User Story 3
- User Story 2 blocks User Story 3 and User Story 4
- User Story 3 blocks User Story 4
- User Story 4 can precede or run partly in parallel with User Story 5 after storage contract is stable
- Cleanup happens after all user stories

### Parallel Opportunities

- T009 to T012 can be grouped before source client implementation
- T019 to T022 can be grouped before comparison implementation
- T049 and T050 can run in parallel near the end
- T051 to T054 can run in parallel near the end

## MVP Definition

A valid MVP for this spec is:
1. healthy Docker stack
2. one live snapshot endpoint
3. one comparison endpoint
4. persisted short-horizon history
5. current host endpoints wired via configuration

## Notes

- consumer contract stability is more important than exposing many BRK metrics
- BRK visual validation is important but is intentionally separated from the live consumer service
- `mempool` and `electrs` remain shared infrastructure, not part of this compose stack
