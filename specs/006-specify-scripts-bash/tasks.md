# Tasks: Real-Time Whale Detection Dashboard

**Branch**: `006-specify-scripts-bash` | **Date**: 2025-11-26 | **Spec**: [spec.md](./spec.md)
**Generated from**: plan.md, data-model.md, contracts/websocket.md, research.md, quickstart.md

## Task Overview

**Total Tasks**: 95 | **Phases**: 10
**Time Estimate**: 3 weeks (1 developer)
**Priority Distribution**: P1 (45%), P2 (35%), P3 (20%)

---

## Phase 1: Infrastructure & Setup (8 tasks)

*Goal: Establish development environment and project structure*

**Independent Test**: Environment variables load, directory structure exists, dependencies install

### Tasks

- [ ] T001 [P1] [SETUP] Create project directory structure as defined in plan.md (`frontend/`, `api/`, `tests/`)
- [ ] T002 [P1] [SETUP] Initialize UV environment with pyproject.toml dependencies (FastAPI, websockets, PyJWT, DuckDB)
- [ ] T003 [P1] [SETUP] Configure .env file with JWT_SECRET, DUCKDB_PATH, MEMPOOL_API_URL
- [ ] T004 [P1] [SETUP] Create .gitignore for Python cache, .env, test outputs
- [ ] T005 [P1] [SETUP] Set up DuckDB database with whale_transactions, net_flow_metrics, alerts tables
- [ ] T006 [P1] [SETUP] Create logging configuration in `api/config.py` with rotation
- [ ] T007 [P2] [SETUP] Write database initialization script `scripts/init_whale_db.py`
- [ ] T008 [P2] [SETUP] Create systemd service file template for FastAPI deployment

**Verification**: `uv run pytest tests/test_setup.py` - all environment checks pass

---

## Phase 2: Authentication & Security (12 tasks)

*Goal: Implement JWT authentication and rate limiting per research.md decisions*

**Independent Test**: JWT tokens generate/validate, rate limiter blocks excessive requests

### Tasks

- [ ] T009 [P1] [FR-007] Create JWT token generator in `api/whale_auth.py` with 1-hour expiry
- [ ] T010 [P1] [FR-007] Implement token validation middleware for WebSocket connections
- [ ] T011 [P1] [FR-007] Create `/api/auth/token` endpoint for initial authentication
- [ ] T012 [P1] [FR-007] Add token refresh mechanism (5 minutes before expiry)
- [ ] T013 [P1] [FR-010] Implement token bucket rate limiter in `api/whale_security.py`
- [ ] T014 [P1] [FR-010] Configure rate limits: 100 req/min HTTP, 20 msg/s WebSocket
- [ ] T015 [P2] [FR-010] Add rate limit headers to HTTP responses (X-RateLimit-*)
- [ ] T016 [P2] [FR-007] Implement connection attempt limiting (5/minute per IP)
- [ ] T017 [P2] [TEST] Write pytest tests for JWT lifecycle in `tests/test_whale_auth.py`
- [ ] T018 [P2] [TEST] Write rate limiting tests in `tests/integration/test_rate_limits.py`
- [ ] T019 [P3] [FR-007] Add token revocation list (Redis optional)
- [ ] T020 [P3] [FR-010] Implement adaptive rate limiting based on load

**Verification**: `uv run pytest tests/test_whale_auth.py tests/test_rate_limits.py`

---

## Phase 3: WebSocket Foundation (10 tasks)

*Goal: Establish WebSocket server with message contracts from contracts/websocket.md*

**Independent Test**: WebSocket connects, authenticates, sends/receives typed messages

### Tasks

- [ ] T021 [P1] [FR-002] Create FastAPI WebSocket endpoint `/ws/whale-alerts` in `api/main.py`
- [ ] T022 [P1] [FR-002] Implement WebSocket connection manager with client tracking
- [ ] T023 [P1] [FR-002] Add Pydantic models for all message types in `api/models/websocket.py`
- [ ] T024 [P1] [FR-002] Implement ping/pong heartbeat (30s interval, 3 missed = disconnect)
- [ ] T025 [P1] [FR-002] Create message router for handling client messages (subscribe, unsubscribe, ping)
- [ ] T026 [P2] [FR-002] Add WebSocket reconnection strategy with exponential backoff
- [ ] T027 [P2] [FR-002] Implement message batching (100ms window, max 10 messages)
- [ ] T028 [P2] [TEST] Write WebSocket integration tests in `tests/integration/test_whale_websocket.py`
- [ ] T029 [P3] [FR-002] Add binary protocol support for high-frequency updates (MessagePack)
- [ ] T030 [P3] [FR-002] Implement permessage-deflate compression

**Verification**: `uv run pytest tests/integration/test_whale_websocket.py`

---

## Phase 4: Data Models & Storage (8 tasks)

*Goal: Implement data models from data-model.md with DuckDB persistence*

**Independent Test**: CRUD operations work for all entities, constraints enforced

### Tasks

- [ ] T031 [P1] [FR-001] Create WhaleTransaction Pydantic model with validation in `api/models/whale.py`
- [ ] T032 [P1] [FR-011] Create NetFlowMetric model with aggregation logic
- [ ] T033 [P1] [FR-004] Create UrgencyScore model with calculation components
- [ ] T034 [P1] [FR-009] Create Alert model with severity levels
- [ ] T035 [P2] [FR-001] Implement DuckDB repository for WhaleTransaction in `api/repositories/whale_repo.py`
- [ ] T036 [P2] [FR-011] Implement NetFlowMetric aggregation queries (1m, 5m, 1h, 24h)
- [ ] T037 [P2] [TEST] Write model validation tests in `tests/test_models.py`
- [ ] T038 [P3] [FR-001] Add data retention policy (30 days transactions, 90 days metrics)

**Verification**: `uv run pytest tests/test_models.py tests/test_repositories.py`

---

## Phase 5: User Story 1 - View Current Whale Activity (P1) (10 tasks)

*Goal: Display current whale net flow and direction indicator*

**Story**: As a trader, I want to see the current whale transaction activity and net flow direction

**Independent Test**: Dashboard loads, displays net flow value, shows direction arrow

### Tasks

#### TDD Phase (Constitution II Compliance)
- [ ] T038a [P1] [TDD-RED] Write failing tests for net flow display component in `tests/test_whale_dashboard.js`
- [ ] T038b [P1] [TDD-RED] Write failing tests for direction indicator logic (accumulation/distribution/neutral)
- [ ] T038c [P1] [TDD-RED] Write failing tests for API endpoint connection and polling mechanism

#### Implementation Phase
- [ ] T039 [P1] [US1] Create `frontend/whale_dashboard.html` with base structure from quickstart.md
- [ ] T040 [P1] [US1] Style dashboard with dark theme in `frontend/css/whale_dashboard.css`
- [ ] T041 [P1] [US1] [FR-001] Create net flow display component (BTC + USD values)
- [ ] T042 [P1] [US1] [FR-001] Add direction indicator (↑ Accumulation, ↓ Distribution, → Neutral)
- [ ] T043 [P1] [US1] [FR-011] Connect to `/api/whale/netflow/current` endpoint
- [ ] T044 [P1] [US1] [FR-011] Update net flow every 5 seconds via polling
- [ ] T045 [P2] [US1] Add loading state and error handling
- [ ] T046 [P2] [US1] Implement number formatting (K, M, B suffixes)
- [ ] T047 [P2] [TEST] Create manual test checklist for dashboard load
- [ ] T048 [P3] [US1] Add color coding (green = accumulation, red = distribution)

#### Refactor Phase
- [ ] T048a [P2] [TDD-REFACTOR] Refactor dashboard code for maintainability while keeping tests green

**Verification**: Open dashboard, verify net flow displays within 3 seconds

---

## Phase 6: User Story 2 - Monitor Real-Time Transactions (P1) (12 tasks)

*Goal: Display live whale transaction feed with WebSocket updates*

**Story**: As a trader, I want to monitor real-time whale transactions as they happen

**Independent Test**: Transactions appear in feed within 5 seconds, auto-scroll works

### Tasks

#### TDD Phase (Constitution II Compliance)
- [ ] T048b [P1] [TDD-RED] Write failing tests for WebSocket connection and authentication
- [ ] T048c [P1] [TDD-RED] Write failing tests for transaction feed display and ring buffer
- [ ] T048d [P1] [TDD-RED] Write failing tests for auto-scroll and pause-on-hover functionality

#### Implementation Phase
- [X] T049 [P1] [US2] Create WebSocket client in `frontend/js/whale_client.js`
- [X] T050 [P1] [US2] [FR-002] Implement WebSocket connection with JWT auth
- [X] T051 [P1] [US2] [FR-002] Handle subscription to 'transactions' channel
- [X] T052 [P1] [US2] [FR-003] Create transaction feed table in `frontend/js/whale_feed.js`
- [X] T053 [P1] [US2] [FR-003] Display: time, amount, direction, urgency, fee rate
- [X] T054 [P1] [US2] [FR-003] Implement ring buffer (max 50 transactions)
- [X] T055 [P1] [US2] [FR-003] Add auto-scroll with pause on hover
- [X] T056 [P2] [US2] Add transaction details modal on row click
- [X] T057 [P2] [US2] Implement transaction filtering (min amount, direction)
- [X] T058 [P2] [TEST] Write WebSocket client integration test
- [X] T059 [P3] [US2] Add CSV export for visible transactions
- [X] T060 [P3] [US2] Add sound notification for large transactions (>500 BTC)

**Verification**: Connect WebSocket, verify transactions appear in real-time

---

## Phase 7: User Story 3 - Analyze Historical Trends (P2) (10 tasks)

*Goal: Display 24-hour whale flow chart with zoom/pan*

**Story**: As a trader, I want to analyze historical whale flow trends to identify patterns

**Independent Test**: Chart loads with data, zoom/pan works, time selector functions

### Tasks

- [X] T061 [P2] [US3] [FR-009] Load Plotly.js basic bundle via CDN in dashboard.html
- [X] T062 [P2] [US3] [FR-009] Create chart container with responsive sizing
- [X] T063 [P2] [US3] [FR-009] Implement line chart in `frontend/js/whale_charts.js`
- [X] T064 [P2] [US3] [FR-006] Add `/api/whale/historical` endpoint with time range
- [X] T065 [P2] [US3] [FR-006] Fetch and display 24-hour data by default
- [X] T066 [P2] [US3] [FR-009] Enable zoom and pan interactions
- [X] T067 [P2] [US3] Add timeframe selector (1h, 6h, 24h, 7d)
- [ ] T068 [P2] [TEST] Test chart performance with 10,000 data points
- [ ] T069 [P3] [US3] Add chart annotations for significant events
- [ ] T070 [P3] [US3] Implement data aggregation for >1000 points

**Verification**: Chart displays, zoom to 1-hour window, verify data updates

---

## Phase 8: User Story 4 - Monitor Transaction Urgency (P2) (8 tasks)

*Goal: Show urgency scores with visual indicators*

**Story**: As a trader, I want to monitor transaction urgency scores to gauge time-sensitivity

**Independent Test**: Urgency scores display, sorting works, color coding applied

### Tasks

- [ ] T071 [P2] [US4] [FR-004] Add urgency column to transaction feed
- [ ] T072 [P2] [US4] [FR-004] Display urgency as progress bar (0-100)
- [ ] T073 [P2] [US4] [FR-004] Color code: red (80+), yellow (50-79), green (<50)
- [ ] T074 [P2] [US4] [FR-008] Add urgency-based sorting option
- [ ] T075 [P2] [US4] [FR-008] Create urgency filter (show only high urgency)
- [ ] T076 [P2] [US4] Add urgency calculation breakdown tooltip
- [ ] T077 [P3] [US4] Add urgency histogram chart
- [ ] T078 [P3] [US4] Create urgency trend indicator

**Verification**: Sort by urgency, verify high-urgency transactions appear first

---

## Phase 9: User Story 5 - Receive Critical Alerts (P3) (9 tasks)

*Goal: Implement multi-channel alert system for extreme movements*

**Story**: As a trader, I want to receive alerts for extreme whale movements

**Independent Test**: Alerts trigger at thresholds, notifications appear, audio plays

### Tasks

- [ ] T079 [P3] [US5] [FR-013] Create alert system in `frontend/js/whale_alerts.js`
- [ ] T080 [P3] [US5] [FR-013] Implement toast notifications (always enabled)
- [ ] T081 [P3] [US5] [FR-013] Request browser notification permission
- [ ] T082 [P3] [US5] [FR-013] Show browser notifications when permitted
- [ ] T083 [P3] [US5] [FR-013] Add alert sound for critical alerts (>500 BTC)
- [ ] T084 [P3] [US5] [FR-013] Create alert configuration panel
- [ ] T085 [P3] [US5] Store alert preferences in localStorage
- [ ] T086 [P3] [TEST] Test alert delivery across browsers
- [ ] T087 [P3] [US5] Add alert history panel (last 10 alerts)

**Verification**: Trigger test alert, verify toast + sound + browser notification

---

## Phase 10: Polish & Cross-Cutting Concerns (8 tasks)

*Goal: Production readiness, performance optimization, documentation*

**Independent Test**: All performance targets met, responsive design works, docs complete

### Tasks

- [ ] T088 [P2] [FR-012] Implement responsive design (mobile, tablet, desktop)
- [ ] T089 [P2] [PERF] Optimize WebSocket message handling for 100 concurrent users
- [ ] T090 [P2] [PERF] Add requestAnimationFrame for smooth UI updates
- [ ] T091 [P2] [PERF] Implement virtual scrolling for transaction feed
- [ ] T092 [P2] [DOC] Create API documentation with examples
- [ ] T093 [P3] [DOC] Write deployment guide for production
- [ ] T094 [P3] [TEST] Create Playwright E2E test suite
- [ ] T095 [P3] [PERF] Add performance monitoring dashboard

**Verification**: Run performance audit, test on mobile, review documentation

---

## Summary Statistics

### Phase Distribution
- **Setup & Foundation** (Phases 1-4): 38 tasks (40%)
- **User Story Implementation** (Phases 5-9): 49 tasks (52%)
- **Polish & Documentation** (Phase 10): 8 tasks (8%)

### Priority Breakdown
- **P1 (Must Have)**: 43 tasks (45%)
- **P2 (Should Have)**: 33 tasks (35%)
- **P3 (Nice to Have)**: 19 tasks (20%)

### Module Distribution
- **Backend (API)**: 35 tasks
- **Frontend (UI)**: 45 tasks
- **Testing**: 15 tasks

### Risk Items
- **T061-T063**: Plotly.js integration may increase bundle size
- **T049-T051**: WebSocket reconnection logic complexity
- **T013-T014**: Rate limiting tuning for production load

---

## Implementation Order Recommendation

### Week 1 (MVP)
1. Phase 1: Infrastructure setup
2. Phase 2: Authentication (critical for security)
3. Phase 3: WebSocket foundation
4. Phase 5: US1 - Basic net flow display

### Week 2 (Core Features)
5. Phase 4: Data models
6. Phase 6: US2 - Real-time feed
7. Phase 7: US3 - Historical charts

### Week 3 (Enhancement & Polish)
8. Phase 8: US4 - Urgency monitoring
9. Phase 9: US5 - Alert system
10. Phase 10: Polish and optimization

---

## Success Metrics

From spec.md success criteria:
- ✅ Dashboard loads in <3 seconds
- ✅ WebSocket latency <50ms
- ✅ 60 FPS UI rendering
- ✅ 100 concurrent users supported
- ✅ Zero external dependencies (frontend)
- ✅ <100MB memory usage
- ✅ 99% uptime with auto-reconnection
- ✅ All whale transactions >100 BTC captured

---

**Next Step**: Run `/speckit.analyze` for cross-artifact consistency check