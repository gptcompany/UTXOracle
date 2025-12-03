# Implementation Plan: Real-time Mempool Whale Detection

**Branch**: `005-mempool-whale-realtime` | **Date**: 2025-11-07 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/005-mempool-whale-realtime/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Build a real-time mempool whale detection system that monitors unconfirmed Bitcoin transactions to provide predictive whale flow signals 10-20 minutes before block confirmation. The system leverages the existing mempool.space WebSocket API to detect whale movements (>100 BTC), calculates urgency scores based on fee rates and RBF status, and broadcasts alerts via WebSocket to dashboard clients with future Redis pub/sub support for NautilusTrader integration.

## Technical Context

**Language/Version**: Python 3.8+ (matches existing UTXOracle stack)
**Primary Dependencies**: websockets (or aiohttp), asyncio, existing WhaleFlowDetector class
**Storage**: DuckDB for 90-day prediction history, in-memory deque for active transactions
**Testing**: pytest with async support, websocket mocking
**Target Platform**: Linux server (same as existing mempool.space Docker stack)
**Project Type**: web (WebSocket server + dashboard extension)
**Performance Goals**: <1 second detection latency, handle 500+ tx/minute stream
**Constraints**: <500MB memory usage, 400MB threshold for graceful degradation
**Scale/Scope**: Monitor all mempool transactions, alert on ~50-100 whale tx/day

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Code Quality & Simplicity ✅
- **KISS/YAGNI**: Reusing existing WhaleFlowDetector, mempool.space WebSocket, and dashboard
- **Single Purpose**: Each module has clear responsibility (WebSocket client, urgency scorer, alert broadcaster)
- **Minimal Dependencies**: Only adding websockets/aiohttp, leveraging existing infrastructure
- **No Premature Optimization**: Starting with simple streaming, optimize if needed
- **No Generic Solutions**: Specific to whale detection use case

### II. Test-First Discipline ✅
- **TDD Cycle**: Will write tests for WebSocket client, urgency scoring, and alert broadcasting
- **Coverage Target**: 80% minimum for new modules
- **Integration Tests**: Required for WebSocket connection, WhaleFlowDetector integration
- **Test Organization**: tests/test_mempool_whale/, tests/integration/test_mempool_realtime.py

### III. User Experience Consistency ✅
- **Dashboard**: Extends existing comparison.html with "Mempool Predictions" section
- **WebSocket API**: JSON messages with Pydantic validation
- **Naming Convention**: Follows existing patterns (MempoolWhaleSignal similar to existing models)
- **Output Format**: Consistent with existing whale flow detection format

### IV. Performance Standards ✅
- **Real-time Latency**: <1 second detection (meets <100ms streaming + <5s estimation requirements)
- **WebSocket Broadcast**: <50ms latency target
- **Resource Limits**: 500MB memory limit with 400MB threshold
- **Logging**: Structured logging with ERROR/WARN/INFO/DEBUG levels

**GATE RESULT**: ✅ PASSED - All constitution principles satisfied

## Project Structure

### Documentation (this feature)

```
specs/005-mempool-whale-realtime/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
│   ├── websocket.yaml   # WebSocket message schemas
│   └── rest-api.yaml    # REST API extensions
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```
# Backend modules (Python)
scripts/
├── mempool_whale_monitor.py     # Main WebSocket client and monitoring service
├── whale_urgency_scorer.py      # Fee-based urgency calculation module
└── whale_alert_broadcaster.py   # Alert distribution via WebSocket/webhooks

api/
└── mempool_whale_endpoints.py   # REST API extensions for historical queries

# Frontend extensions (JavaScript)
frontend/
├── js/
│   └── mempool_predictions.js   # WebSocket client and UI updates
└── comparison.html              # Extended dashboard with mempool section

# Tests
tests/
├── integration/
│   └── test_mempool_realtime.py # End-to-end WebSocket flow tests
└── test_mempool_whale/
    ├── test_monitor.py          # Unit tests for monitoring service
    ├── test_urgency_scorer.py   # Unit tests for urgency calculations
    └── test_broadcaster.py      # Unit tests for alert broadcasting

# Data storage
data/
└── mempool_predictions.db       # DuckDB database for 90-day history
```

**Structure Decision**: Web application structure chosen due to WebSocket server + dashboard frontend components. Modules organized in existing `scripts/` directory to maintain consistency with current WhaleFlowDetector location. Frontend extensions go in existing `frontend/` directory. Tests follow pytest convention with dedicated test module directory.

## Complexity Tracking

*No violations - all constitution principles satisfied.*

