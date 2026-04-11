# Tasks: spec-054 Production Boundary and Surface Tiering

**Input**: design documents from `/specs/054-production-boundary-and-surface-tiering/`
**Prerequisites**: `spec.md`, `plan.md`

## Format: `[ID] [Markers] Description`

### Task Markers
- **[P]**: can run in parallel
- **[E]**: boundary or contract-impacting change

---

## Phase 1: Baseline and Drift Inventory

- [x] T001 Freeze the scope: this spec governs service boundary and execution eligibility, not strategy logic or broad auth redesign
- [x] T002 [P] Inventory all route families currently mounted on `:8011` — AC: produce a table of every route prefix, HTTP method, and source module; done when verified against `api/apps/live.py` route registrations
- [x] T003 [P] Inventory the documented `:8011` production boundary across README, service profile, and contract docs — AC: one diff table showing each doc's claim vs runtime
- [x] T004 Record all drift between runtime exposure and documentation — AC: drift list with file:line references for each mismatch
- [x] T005 Record the current consumer assumption that `NT` should only use a narrow subset of the available API — AC: statement logged in decisions.md

**Checkpoint**: the real boundary problem is explicit before tiering starts.

---

## Phase 2: Tier Model Freeze

- [x] T006 Freeze the tier vocabulary to exactly `tier_1_execution`, `tier_2_operator`, and `tier_3_research`
- [x] T007 Freeze the semantic definition of each tier
- [x] T008 Freeze the rule that `NT` may consume only `tier_1_execution`
- [x] T009 Decide how `:8001` is classified in the tier model
- [x] T010 Decide the first-slice treatment of `tier_2_operator` and exceptional `tier_3_research` routes that remain exposed on `:8011`
- [x] T011 Freeze the approval rule for future tier changes

**Checkpoint**: the tier system is narrow and binding.

---

## Phase 3: Route-Family Assignment

- [x] T012 [E] Classify `/health` and `/api/v1/live/*`
- [x] T013 [E] Classify `/api/features/btc/*` and `/api/signals/btc/*`
- [x] T014 [E] Classify `/api/prices/*` and `/api/metrics/latest`
- [x] T015 [E] Classify `/api/metrics/address-cohorts`, `/cost-basis`, `/wallet-waves`, and `/absorption-rates`
- [x] T016 [E] Classify `/api/whale/*` and `/api/entities/*`
- [x] T017 [E] Classify `/api/v1/charts/*`, `/charts/*`, `/api/meta/features`, and `/api/research/tier-stats`
- [x] T018 Record allowed consumers for each classified family: `NT`, operator, research, or mixed non-execution

**Checkpoint**: every exposed family belongs to exactly one tier.

---

## Phase 4: Boundary Artifact and Documentation

- [ ] T019 Create one canonical boundary artifact at `docs/contracts/surface_boundary.yaml` listing route family, host, tier, allowed consumers, source of truth, fail mode, and execution eligibility
- [ ] T020 Update the production consumer service profile to align with the frozen tier model
- [ ] T021 Update the README so the documented `:8011` boundary matches the chosen contract truth
- [ ] T022 Update the feature contract registry and related docs to reflect the frozen tier assignments
- [ ] T023 Define the canonical doc or artifact that must be updated before any future boundary expansion

**Checkpoint**: docs and boundary policy are synchronized.

---

## Phase 5: Runtime and Policy Alignment

- [ ] T024 [E] Decide whether any currently exposed `tier_2_operator` or `tier_3_research` families should be removed from `:8011` immediately
- [ ] T025 [E] If non-execution families remain exposed on `:8011`, add explicit non-execution documentation and/or tags
- [ ] T026 [E] Ensure no execution-facing doc instructs `NT` to read `tier_2_operator` or `tier_3_research` routes
- [ ] T027 Define the change-control rule for promoting a family from `tier_2_operator` to `tier_1_execution`
- [ ] T028 Record the boundary decision as the required dependency for `spec-055`

**Checkpoint**: the service boundary is now explicit enough to support an execution contract.

---

## Phase 6: Verification

- [ ] T029 Verify every `:8011` route family is classified exactly once
- [ ] T030 Verify README, service profile, and registry no longer contradict runtime exposure
- [ ] T031 Verify `NT` guidance references only `tier_1_execution`
- [ ] T032 Verify no unclassified family remains implied as production-consumable
- [ ] T033 Verify the boundary artifact is small, reviewable, and future-proof enough to stay maintained

**Checkpoint**: the production boundary is frozen and reviewable.
