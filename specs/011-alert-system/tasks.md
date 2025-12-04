# Tasks: Webhook Alert System

**Input**: Design documents from `/specs/011-alert-system/`

## Format: `[ID] [P?] [Story] Description`

## User Story Mapping (spec.md alignment)

| Spec US | Description | Tasks Phase |
|---------|-------------|-------------|
| US1 | Webhook Configuration | Phase 3 |
| US2 | Whale Event Emission | Phase 4 |
| US3 | Signal Event Emission | Phase 4 |
| US4 | Regime Event Emission | Phase 4 |
| US5 | Price Divergence Event | Phase 4 |

---

## Phase 1: Setup

- [X] T001 Create scripts/alerts/ directory structure
- [X] T002 [P] Create scripts/alerts/__init__.py with public API stubs
- [X] T003 [P] Create empty tests/test_alerts.py

---

## Phase 2: Data Models

### Tests (TDD RED)
- [X] T004 [P] Write test_alert_event_serialization() in tests/test_alerts.py
- [X] T005 [P] Write test_webhook_config_from_env() in tests/test_alerts.py
- [X] T006 [P] Write test_webhook_delivery_status_transitions() in tests/test_alerts.py

### Implementation (TDD GREEN)
- [X] T007 Implement AlertEvent dataclass in scripts/alerts/models.py
- [X] T008 Implement WebhookConfig dataclass with from_env() in scripts/alerts/models.py
- [X] T009 Implement WebhookDelivery dataclass in scripts/alerts/models.py
- [X] T010 Run tests - verify T004-T006 pass

**Checkpoint**: Data models complete

---

## Phase 3: Webhook Dispatcher (US1) 🎯 MVP

**Goal**: HTTP POST with HMAC signing and retry logic

### Tests (TDD RED)
- [X] T011 [P] [US1] Write test_dispatcher_posts_to_webhook() in tests/test_alerts.py
- [X] T012 [P] [US1] Write test_dispatcher_signs_request_when_secret_set() in tests/test_alerts.py
- [X] T013 [P] [US1] Write test_dispatcher_retries_on_failure() in tests/test_alerts.py
- [X] T014 [P] [US1] Write test_dispatcher_respects_timeout() in tests/test_alerts.py
- [X] T015 [P] [US1] Write test_dispatcher_skips_when_disabled() in tests/test_alerts.py

### Implementation (TDD GREEN)
- [X] T016 [US1] Implement WebhookDispatcher class in scripts/alerts/dispatcher.py
- [X] T017 [US1] Implement _sign() method for HMAC-SHA256 in dispatcher.py
- [X] T018 [US1] Implement retry logic with exponential backoff in dispatcher.py
- [X] T019 [US1] Run tests - verify T011-T015 pass

**Checkpoint**: Webhook dispatcher working

---

## Phase 4: Event Generators (US2-US5)

**Goal**: Factory functions for whale, signal, regime, price events

### Tests (TDD RED)
- [X] T020 [P] [US2] Write test_create_whale_event() in tests/test_alerts.py
- [X] T021 [P] [US2] Write test_whale_event_severity_by_amount() in tests/test_alerts.py
- [X] T022 [P] [US3] Write test_create_signal_event() in tests/test_alerts.py
- [X] T023 [P] [US3] Write test_signal_event_excludes_hold() in tests/test_alerts.py
- [X] T024 [P] [US4] Write test_create_regime_event() in tests/test_alerts.py
- [X] T025 [P] [US5] Write test_create_price_event() in tests/test_alerts.py

### Implementation (TDD GREEN)
- [X] T026 [US2] Implement create_whale_event() in scripts/alerts/generators.py
- [X] T027 [US3] Implement create_signal_event() in scripts/alerts/generators.py
- [X] T028 [US4] Implement create_regime_event() in scripts/alerts/generators.py
- [X] T029 [US5] Implement create_price_event() in scripts/alerts/generators.py
- [X] T030 Run tests - verify T020-T025 pass

**Checkpoint**: Event generators working

---

## Phase 5: Persistence

**Goal**: Log all events to DuckDB for audit/replay

### Tests (TDD RED)
- [X] T031 [P] Write test_save_event_to_db() in tests/test_alerts.py
- [X] T032 [P] Write test_update_event_webhook_status() in tests/test_alerts.py
- [X] T033 [P] Write test_get_failed_events_for_replay() in tests/test_alerts.py

### Implementation (TDD GREEN)
- [X] T034 Add alert_events table to scripts/init_metrics_db.py
- [X] T035 Implement save_event() in scripts/alerts/__init__.py
- [X] T036 Implement update_webhook_status() in scripts/alerts/__init__.py
- [X] T037 Implement get_failed_events() in scripts/alerts/__init__.py
- [X] T038 Run tests - verify T031-T033 pass

**Checkpoint**: Persistence working

---

## Phase 6: Integration

- [X] T039 Implement emit_alert() public API in scripts/alerts/__init__.py
- [X] T040 Hook alert emission into daily_analysis.py after fusion (FR-015)
- [X] T041 Add ALERT_* environment variables to .env.example

---

## Phase 7: N8N Template

- [X] T042 Create examples/n8n/ directory
- [X] T043 Create examples/n8n/utxoracle-alerts.json workflow template
- [X] T044 Document N8N setup in quickstart.md (already done)

---

## Phase 8: Polish

- [X] T045 [P] Add module docstrings to all alert modules
- [X] T046 [P] Export public API from scripts/alerts/__init__.py
- [X] T047 Run full test suite - verify ≥85% coverage (SC-005) - **89% achieved**
- [X] T048 Create integration test tests/integration/test_alerts_webhook.py

---

## Dependencies

```
Phase 1 (Setup)       → No dependencies
Phase 2 (Models)      → Phase 1
Phase 3 (Dispatcher)  → Phase 2 🎯 MVP
Phase 4 (Generators)  → Phase 2
Phase 5 (Persistence) → Phase 2
Phase 6 (Integration) → Phase 3, Phase 4, Phase 5
Phase 7 (N8N)         → Phase 3
Phase 8 (Polish)      → All previous
```

---

## Requirements Coverage Matrix

| Requirement | Task(s) | Status |
|-------------|---------|--------|
| FR-001 (webhook URL config) | T005, T008, T041 | ✅ |
| FR-002 (HMAC signing) | T012, T017 | ✅ |
| FR-003 (JSON schema) | T004, T007 | ✅ |
| FR-004 (event metadata) | T007 | ✅ |
| FR-005 (whale payload) | T020-T021, T026 | ✅ |
| FR-006 (signal payload) | T022-T023, T027 | ✅ |
| FR-007 (regime payload) | T024, T028 | ✅ |
| FR-008 (price payload) | T025, T029 | ✅ |
| FR-009 (severity filter) | T005, T008 | ✅ |
| FR-010 (event toggles) | T005, T008 | ✅ |
| FR-011 (default thresholds) | T008 | ✅ |
| FR-012 (retry logic) | T013, T018 | ✅ |
| FR-013 (DuckDB logging) | T031-T037 | ✅ |
| FR-014 (graceful degradation) | T015, T016 | ✅ |
| FR-015 (daily_analysis hook) | T040 | ✅ |
| FR-016 (whale_detector hook) | - | ⏳ Future |
| NFR-001 (latency <100ms) | T047 | ✅ |
| NFR-002 (timeout 5s) | T014, T016 | ✅ |
| NFR-003 (rate limit 60/min) | T016 | ✅ |
| NFR-004 (zero new deps) | - | ✅ |

---

## Summary

| Phase | Tasks |
|-------|-------|
| Setup | 3 |
| Models | 7 |
| Dispatcher | 9 |
| Generators | 11 |
| Persistence | 8 |
| Integration | 3 |
| N8N Template | 3 |
| Polish | 4 |
| **Total** | **48** |

---

## Comparison: v1 (Telegram Bot) vs v2 (Webhook)

| Metric | v1 Telegram Bot | v2 Webhook |
|--------|-----------------|------------|
| Tasks | 98 | **48** |
| New Dependencies | 1 (python-telegram-bot) | **0** |
| Estimated LOC | ~600 | **~150** |
| Channels Supported | 1 (Telegram) | **Unlimited** |
| User Management | In UTXOracle | **In N8N** |
| Rate Limiting | Custom impl | **N8N built-in** |

**Reduction**: 51% fewer tasks, 75% less code, unlimited flexibility.
