# Implementation Plan: Webhook Alert System

**Branch**: `011-alert-system` | **Date**: 2025-12-04 | **Spec**: [spec.md](./spec.md)

## Summary

Implement a webhook-based alert system for UTXOracle signals. Emit structured JSON events to configurable endpoints (N8N, Zapier, custom). Support whale movements, regime changes, high-confidence signals, and price divergence alerts.

**Primary Value**: Event-driven architecture leveraging existing N8N infrastructure.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: None new (httpx already in project)
**Storage**: DuckDB (alert_events table for audit/replay)
**Testing**: pytest with httpx mock
**Performance Goals**: <100ms event emission (excluding network)
**Constraints**: Single webhook endpoint, N8N handles fanout

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. KISS/YAGNI | ✅ PASS | Zero new dependencies, ~150 LOC vs ~600 for Telegram bot |
| II. TDD | ✅ PASS | All phases have TDD RED→GREEN pattern |
| III. UX Consistency | ✅ PASS | JSON contract, environment config |
| IV. Performance | ✅ PASS | <100ms emission latency |
| V. Data Privacy | ✅ PASS | Local processing, user controls webhook destination |

## Project Structure

```
scripts/
├── alerts/
│   ├── __init__.py          # Public API: emit_alert(), get_config()
│   ├── models.py             # AlertEvent, WebhookConfig, WebhookDelivery
│   ├── dispatcher.py         # WebhookDispatcher (HTTP POST, retry)
│   └── generators.py         # create_whale_event(), create_signal_event(), etc.

examples/
└── n8n/
    └── utxoracle-alerts.json # N8N workflow template

tests/
├── test_alerts.py            # Unit tests
└── integration/
    └── test_alerts_webhook.py # Integration test with mock server
```

## Phase 0: Research

See [research.md](./research.md) - KISS analysis of Bot vs Webhook approach.

## Phase 1: Design

See [data-model.md](./data-model.md), [quickstart.md](./quickstart.md)

## Implementation Phases

### Phase 1: Setup (T001-T003)
- Create directory structure
- Initialize modules
- Setup test file

### Phase 2: Models (T004-T009)
- TDD for AlertEvent, WebhookConfig, WebhookDelivery
- JSON serialization

### Phase 3: Webhook Dispatcher (T010-T016)
- TDD for HTTP POST
- HMAC signing
- Retry logic with exponential backoff

### Phase 4: Event Generators (T017-T024)
- TDD for whale, signal, regime, price events
- Threshold filtering

### Phase 5: Persistence (T025-T028)
- TDD for DuckDB logging
- Event replay support

### Phase 6: Integration (T029-T031)
- Hook into daily_analysis.py
- Environment configuration

### Phase 7: N8N Template (T032-T033)
- Create workflow template
- Documentation

### Phase 8: Polish (T034-T037)
- Coverage verification
- Integration test
- Cleanup

## Dependencies

```
Phase 1 (Setup)      → No dependencies
Phase 2 (Models)     → Phase 1
Phase 3 (Dispatcher) → Phase 2 🎯 MVP
Phase 4 (Generators) → Phase 2
Phase 5 (Persistence)→ Phase 2
Phase 6 (Integration)→ Phase 3, Phase 4, Phase 5
Phase 7 (N8N)        → Phase 3
Phase 8 (Polish)     → All previous
```

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Webhook endpoint unreachable | Retry 3x, log to DuckDB for replay |
| Event flood | Rate limit 60/min, queue excess |
| Schema changes | Version in payload, backwards compatible |
