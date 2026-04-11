# Tasks: spec-056 Service SLO, Freshness, and Capacity

**Input**: design documents from `/specs/056-service-slo-freshness-and-capacity/`
**Prerequisites**: `spec.md`, `plan.md`, `spec-054`

## Format: `[ID] [Markers] Description`

### Task Markers
- **[P]**: can run in parallel
- **[E]**: execution-impacting operational contract change

---

## Phase 1: SLO Scope Freeze

- [x] T001 Freeze the scope: this spec covers tier-1 execution-grade targets, not commercial public-API SLA promises
- [x] T002 Freeze the rule that strict SLOs apply only to `tier_1_execution` surfaces in the first slice
- [x] T003 Freeze the local single-host deployment assumption
- [x] T004 Record which tier-1 routes require explicit latency, freshness, and availability targets, including the future execution-status route from `spec-055`
- [x] T005 Decide which route families remain best-effort operator surfaces outside the strict SLO set

**Checkpoint**: the scope of strict service guarantees is narrow and credible.

---

## Phase 2: Freshness Model

- [x] T006 Freeze the freshness vocabulary to `healthy`, `degraded`, `stale`
- [x] T007 Freeze the healthy freshness target for live snapshots
- [x] T008 Freeze the healthy freshness target for feature bundles
- [x] T009 Freeze the healthy freshness target for signal snapshots
- [x] T010 Freeze the maximum tolerated stale threshold for each tier-1 input class
- [x] T011 Align route semantics so the same freshness classes mean the same thing across tier-1 surfaces

**Checkpoint**: freshness semantics are numeric and uniform.

---

## Phase 3: Latency and Availability Targets

- [x] T012 Freeze p95 latency target for `GET /health`
- [x] T013 Freeze p95 latency target for tier-1 `latest` reads
- [x] T014 Freeze p95 latency target for bounded tier-1 `history` reads
- [x] T015 Freeze the monthly availability target for `tier_1_execution`
- [x] T016 Define which target violations are warning-only and which are execution-relevant

**Checkpoint**: service performance expectations are explicit.

---

## Phase 4: Capacity Assumption

- [x] T017 Freeze the intended consumer model: one serious `NT` consumer plus light operator load
- [x] T018 Define burst, retry, and polling-cadence assumptions for the first slice
- [x] T019 Define what load model is explicitly out of scope
- [x] T020 Decide what simple local measurements are sufficient to verify the capacity assumptions

**Checkpoint**: capacity promises match the real intended deployment.

---

## Phase 5: Governance and Coupling

- [x] T021 Publish one canonical SLO artifact or doc section containing the frozen numeric targets
- [x] T022 Define how stale or violated tier-1 targets feed `spec-055` execution modes
- [x] T023 Define how SLO violations feed `spec-059` alerting and incident severity
- [x] T024 Update service docs so operators know which numbers are targets versus hard execution blockers

**Checkpoint**: SLOs are not just numbers; they have operational consequences.

---

## Phase 6: Verification

- [x] T025 Verify all tier-1 routes referenced in `spec-055` have explicit numeric targets
- [x] T026 Verify no tier-2 or research-only family receives accidental execution-grade promises
- [x] T027 Verify freshness thresholds are compatible with real producer cadence
- [x] T028 Verify the capacity story remains simple enough for a single-operator setup
- [x] T029 Verify the SLO artifact is small and maintainable

**Checkpoint**: the service guarantee layer is usable in operations and execution gating.
