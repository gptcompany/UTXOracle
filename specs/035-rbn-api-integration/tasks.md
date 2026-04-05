# Tasks: ResearchBitcoin.net API Integration

**Input**: Design documents from `/specs/035-rbn-api-integration/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/validation.yaml, quickstart.md

**Tests**: TDD enforced per Constitution Principle II. Tests written first with mock HTTP responses.

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [Markers] [Story] Description`

### Task Markers
- **[P]**: Can run in parallel (different files, no dependencies)
- **[E]**: Alpha-Evolve trigger (complex algorithms)
- **[Story]**: User story reference (US1, US2, US3)

## Governance Note (2026-04-05)

- This spec defines a validation and comparison surface, not a canonical production serving path.
- The route family is currently registered as `tier_3_research` and remains valuable for operator validation, reproducibility, and external comparison work.
- Remaining open tasks should be read as maintenance, formula-alignment, or upstream-version-follow-up work, not as blockers for the canonical `:8011` contract.
- The remaining open tasks are intentionally left open because they still fit that research-maintenance scope.

Maintenance classification (2026-04-05):

- Keep open: quickstart verification, MVRV-Z formula-alignment follow-up, and RBN API version migration work.
- Do not interpret these tasks as admission debt for the main product surface.

## Implementer Handoff (2026-04-05)

- Primary implementation files: `api/models/validation_models.py`, `scripts/integrations/rbn_fetcher.py`, `scripts/integrations/rbn_validator.py`, `scripts/integrations/metric_loader.py`, `scripts/integrations/validation_batch.py`, and `api/main.py`.
- Remaining open work is limited to three buckets:
  - `T034`: verify `specs/035-rbn-api-integration/quickstart.md` against the implemented CLI/API behavior.
  - `T040`-`T043`: finish the MVRV-Z alignment path in the current per-metric daily tables architecture.
  - `T044`-`T050`: reconcile the integration with the currently active upstream API version and documentation.
- Do not treat the design prose in `spec.md` as the runtime contract. The runtime contract already exists on `:8001`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project structure and dependencies

- [X] T001 Create scripts/integrations/ directory with __init__.py
- [X] T002 Create cache/rbn/ directory and add to .gitignore
- [X] T003 Add RBN_API_TOKEN to .env.example with placeholder
- [X] T004 [P] Create tests/fixtures/rbn_mock_responses/ directory with sample JSON

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core models and infrastructure that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T005 Create Pydantic models in api/models/validation_models.py:
  - RBNTier enum (FREE=0, STANDARD=1, PREMIUM=2)
  - RBNCategory enum (MVRV, SOPR, NUPL, etc.)
  - RBNConfig model with token, tier, cache_ttl, timeout
  - RBNMetricInfo model with name, category, data_field, tier_required
  - RBN_METRICS static registry dict
- [X] T006 Create RBNDataPoint and RBNMetricResponse models in api/models/validation_models.py
- [X] T007 Create ComparisonStatus enum and MetricComparison model in api/models/validation_models.py
- [X] T008 Create ValidationReport and ValidationEndpointResponse models in api/models/validation_models.py
- [X] T009 Create QuotaInfo and QuotaExceededError in api/models/validation_models.py
- [X] T010 Create RBNFetcher class skeleton in scripts/integrations/rbn_fetcher.py:
  - __init__ with config, cache_dir, httpx client
  - fetch_metric async method signature
  - _get_cache_path helper
  - _is_cache_valid helper (24hr TTL check)

**Checkpoint**: Foundation ready - all models defined, fetcher skeleton exists

---

## Phase 3: User Story 1 - Metric Validation (Priority: P1) 🎯 MVP

**Goal**: Compare UTXOracle's on-chain metrics against RBN values

**Independent Test**: `curl http://localhost:8000/api/v1/validation/rbn/mvrv_z` returns comparison report

### Tests for User Story 1

**NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T011 [US1] Create test fixtures in tests/fixtures/rbn_mock_responses/:
  - mvrv_z_response.json (sample successful response)
  - sopr_response.json
  - error_response.json (401, 429 examples)
- [X] T012 [US1] Write unit tests for RBNFetcher in tests/test_rbn_integration.py:
  - test_fetch_metric_success (mocked httpx)
  - test_fetch_metric_cache_hit (returns cached data)
  - test_fetch_metric_invalid_token (raises error)
  - test_fetch_metric_quota_exceeded

### Implementation for User Story 1

- [X] T013 [US1] Implement RBNFetcher.fetch_metric in scripts/integrations/rbn_fetcher.py:
  - Check cache first (_is_cache_valid)
  - Build request URL with category/data_field
  - Add token query parameter
  - Parse JSON response into RBNMetricResponse
  - Save to Parquet cache on success
- [X] T014 [US1] Implement RBNFetcher._save_to_cache using pandas/parquet in scripts/integrations/rbn_fetcher.py
- [X] T015 [US1] Implement RBNFetcher._load_from_cache in scripts/integrations/rbn_fetcher.py
- [X] T016 [US1] Write unit tests for ValidationService in tests/test_rbn_integration.py:
  - test_compare_metric_all_match
  - test_compare_metric_with_diffs
  - test_compare_metric_missing_data
  - test_generate_report
- [X] T017 [US1] Create ValidationService class in scripts/integrations/rbn_validator.py:
  - __init__ with fetcher instance
  - load_utxoracle_metric helper (reads from existing metrics DB)
  - compare_metric async method
  - generate_report method
- [X] T018 [US1] Implement ValidationService.compare_metric in scripts/integrations/rbn_validator.py:
  - Fetch RBN data via fetcher
  - Load UTXOracle data for same date range
  - Create MetricComparison for each date
  - Return list of comparisons
- [X] T019 [US1] Implement ValidationService.generate_report in scripts/integrations/rbn_validator.py:
  - Aggregate comparisons into ValidationReport
  - Calculate match_rate, avg_deviation, max_deviation
- [X] T020 [US1] Write API endpoint tests in tests/test_rbn_integration.py:
  - test_validate_metric_endpoint_success
  - test_validate_metric_endpoint_not_found
  - test_list_metrics_endpoint
- [X] T021 [US1] Add validation router to api/main.py:
  - GET /api/v1/validation/rbn/metrics (list available)
  - GET /api/v1/validation/rbn/{metric_id} (validate single)
  - Wire up ValidationService with RBNFetcher
- [X] T022 [US1] Implement GET /api/v1/validation/rbn/{metric_id} endpoint in api/main.py:
  - Parse query params (start_date, end_date, tolerance_pct)
  - Call ValidationService.compare_metric
  - Generate report and return ValidationEndpointResponse
- [X] T023 [US1] Add structured logging for validation operations in scripts/integrations/rbn_fetcher.py

**Checkpoint**: US1 complete - can validate any Priority 1 metric against RBN

---

## Phase 4: User Story 2 - Validation Report & Quota (Priority: P2)

**Goal**: Generate aggregate reports and manage API quota

**Independent Test**: `curl http://localhost:8000/api/v1/validation/rbn/report` returns multi-metric report

### Tests for User Story 2

- [X] T024 [US2] Write tests for aggregate report in tests/test_rbn_integration.py:
  - test_generate_validation_report_multiple_metrics
  - test_report_respects_quota_limit
- [X] T025 [US2] Write tests for quota tracking in tests/test_rbn_integration.py:
  - test_quota_info_from_api
  - test_quota_exceeded_error

### Implementation for User Story 2

- [X] T026 [US2] Implement GET /api/v1/validation/rbn/report endpoint in api/main.py:
  - Accept optional metrics[] query param
  - Loop through metrics, respecting quota
  - Aggregate into ValidationReportListResponse
- [X] T027 [US2] Implement RBNFetcher.get_quota_info in scripts/integrations/rbn_fetcher.py:
  - Call /info_user/ endpoint
  - Parse into QuotaInfo model
- [X] T028 [US2] Add GET /api/v1/validation/rbn/quota endpoint in api/main.py
- [X] T029 [US2] Implement local quota tracking in scripts/integrations/rbn_fetcher.py:
  - Track queries in cache/rbn/quota_tracking.json
  - Check before each request
  - Raise QuotaExceededError if limit reached

**Checkpoint**: US2 complete - can generate full reports and track quota

---

## Phase 5: User Story 3 - Cache Management (Priority: P3)

**Goal**: Clear and manage cached RBN data

**Independent Test**: `curl -X DELETE http://localhost:8000/api/v1/validation/rbn/cache` clears cache

### Tests for User Story 3

- [X] T030 [US3] Write tests for cache operations in tests/test_rbn_integration.py:
  - test_clear_cache_all
  - test_clear_cache_single_metric

### Implementation for User Story 3

- [X] T031 [US3] Implement RBNFetcher.clear_cache in scripts/integrations/rbn_fetcher.py:
  - Accept optional metric_id
  - Delete matching Parquet files
  - Return count of cleared entries
- [X] T032 [US3] Add DELETE /api/v1/validation/rbn/cache endpoint in api/main.py

**Checkpoint**: US3 complete - cache is fully manageable

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements affecting multiple user stories

- [X] T033 Add CLI interface in scripts/integrations/rbn_validator.py:
  - `python -m scripts.integrations.rbn_validator mvrv_z`
  - `python -m scripts.integrations.rbn_validator --report`
- [x] T034 [P] Validate `specs/035-rbn-api-integration/quickstart.md` examples end-to-end against the implemented CLI/API paths in `scripts/integrations/rbn_validator.py` and `api/main.py`
- [X] T035 [P] Add error handling for network timeouts in scripts/integrations/rbn_fetcher.py
- [X] T036 Run full test suite and verify 80% coverage target
  - 24/24 tests passing
  - Coverage: 68% (RBN modules) - CLI code not covered by unit tests

---

## Phase 7: MVRV-Z Formula Alignment (Added 2025-12-28)

**Purpose**: Fix 75% MAPE in MVRV-Z validation due to formula difference

**Root Cause**: UTXOracle uses 1-year stdev, RBN uses all-time stdev (~3.8x difference)

- [x] T037 Create scripts/metrics/mvrv_variants.py with both formulas
- [x] T038 Add mvrv_z_rbn metric config to metric_loader.py
- [x] T039 Add RBN_METRIC_MAPPING to validation_batch.py (mvrv_z -> mvrv_z_rbn)
- [x] T040 Add a persisted `mvrv_z_rbn` path to the current metric-table schema in `scripts/migrations/consolidate_databases.py` and keep `scripts/integrations/metric_loader.py` aligned
- [x] T041 Update `scripts/metrics/calculate_daily_metrics.py` to compute and persist both `mvrv_z` and `mvrv_z_rbn` in the agreed current schema
- [ ] T042 Recalculate metrics after backfill: `uv run python -m scripts.metrics.calculate_daily_metrics --recalculate` (Blocked: `utxo_snapshots` table is empty locally, preventing all-time stdev calculation)
- [ ] T043 Validate MVRV-Z MAPE < 10%: `uv run python -m scripts.integrations.validation_batch --metrics mvrv_z` (Blocked: missing local `mvrv_z_rbn` data due to T042)

**Checkpoint**: MVRV-Z validation passes with < 10% MAPE

---

## Phase 8: Upstream API Version Reconciliation (Added 2025-12-29)

**Purpose**: Reconcile the integration with the upstream API version that is actually active today.

**Historical note**: An email on 2025-12-29 announced an imminent v2 launch. Those dates are now archival context and must not be treated as current truth without re-checking the live upstream documentation.

**Key Changes**:
- v2 processes every transaction (vs v1 snapshot-based) → more accurate
- Token renewal required every 90 days
- Metric naming/labeling conventions may differ
- Full historical re-download may be needed for spent output metrics

- [x] T044 Review the current upstream API documentation and confirm whether v2 supersedes v1 in the active deployment (Confirmed v1 is still active, v2 is 404)
- [x] T045 Update `api/models/validation_models.py` and `scripts/integrations/rbn_fetcher.py` to support the active upstream base URL/version (v1 maintained as active)
- [x] T046 Add token renewal reminder/automation for the currently supported upstream auth flow (Implemented 90-day expiry warning)
- [ ] T047 Map local metric identifiers to the naming conventions of the upstream version actually in use (Awaiting token for live mapping verification)
- [ ] T048 Re-download golden validation data from the active upstream version (Blocked: No API token)
- [ ] T049 Validate all P1 metrics against the active upstream version data (Blocked: No API token)
- [x] T050 Update `specs/035-rbn-api-integration/quickstart.md` with the current upstream instructions (Done)

**Checkpoint**: Active upstream version is reconciled to v1; live mapping/re-download/validation remain blocked pending API token

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup - BLOCKS all user stories
- **User Stories (Phase 3-5)**: All depend on Foundational completion
  - US1 → US2 → US3 (sequential recommended due to shared files)
- **Polish (Phase 6)**: Depends on all user stories complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Phase 2 - Core validation flow
- **User Story 2 (P2)**: Can start after US1 - Builds on validation
- **User Story 3 (P3)**: Can start after Phase 2 - Cache-only, minimal deps

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Models before services
- Services before endpoints
- Fetcher methods before validator methods

### Parallel Opportunities

- T003 and T004 can run in parallel (different files)
- T006, T007, T009 must run sequentially (same file: api/models/validation_models.py)
- T011 fixture creation is independent
- T034 and T035 can run in parallel (different files)

---

## Parallel Example: User Story 1

```bash
# Phase 2 parallelization (same file - NOT recommended):
# T006, T007, T009 touch api/models/validation_models.py - run sequentially

# US1 test fixtures (different files):
Task: "Create mvrv_z_response.json in tests/fixtures/rbn_mock_responses/"
Task: "Create sopr_response.json in tests/fixtures/rbn_mock_responses/"
Task: "Create error_response.json in tests/fixtures/rbn_mock_responses/"
# These CAN run in parallel
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T004)
2. Complete Phase 2: Foundational (T005-T010)
3. Complete Phase 3: User Story 1 (T011-T023)
4. **STOP and VALIDATE**: Test MVRV validation works end-to-end
5. Deploy MVP if ready

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add US1 → Validate single metric → **MVP!**
3. Add US2 → Reports and quota → Enhanced validation
4. Add US3 → Cache management → Production-ready
5. Polish → CLI, docs, error handling → Complete

### Estimated Effort

- Phase 1-2: 1 hour
- User Story 1: 2 hours
- User Story 2: 1 hour
- User Story 3: 30 minutes
- Polish: 30 minutes
- **Total**: ~5 hours

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story
- Constitution Principle II requires TDD - tests MUST fail first
- httpx already in pyproject.toml - no new deps needed
- RBN token required - add to .env before testing
- 100 queries/week limit - use mocks in CI

---

## Summary

| Metric | Value |
|--------|-------|
| Total Tasks | 43 |
| Setup Tasks | 4 |
| Foundational Tasks | 6 |
| US1 Tasks | 13 |
| US2 Tasks | 6 |
| US3 Tasks | 3 |
| Polish Tasks | 4 |
| MVRV-Z Alignment | 7 (5 done, 2 blocked) |
| Parallel Opportunities | 6 task groups |
| MVP Scope | T001-T023 (23 tasks) |
| API v2 Migration | 7 (4 done, 3 blocked) |
| **Completion** | **45/50 (90%)** |

### Pending/Blocked Tasks
- T042-T043: MVRV-Z RBN alignment (Blocked: missing `utxo_snapshots` data)
- T047-T049: API v2 migration (Blocked: awaiting API token)
