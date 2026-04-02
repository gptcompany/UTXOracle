# Tasks: spec-049 Feature Research Admission Gate

**Input**: design documents from `/specs/049-feature-research-admission-gate/`
**Prerequisites**: `spec.md`, `plan.md`

## Format: `[ID] [Markers] Description`

### Task Markers
- **[P]**: can run in parallel
- **[E]**: complex decision or contract-model task

---

## Phase 1: Scope Freeze

- [x] T001 Freeze the post-`M6` candidate set to `nupl_surface` and `cost_basis_surface`
- [x] T002 Record `reserve-risk` as explicitly out of scope for the admission gate
- [x] T003 Publish the admission-governance baseline document

**Checkpoint**: the post-`M6` gate is bounded and no route drifts into scope implicitly.

---

## Phase 2: Evidence Inventory

- [x] T004 Inventory runtime and degraded semantics for `nupl_surface`
- [x] T005 Inventory runtime and degraded semantics for `cost_basis_surface`
- [x] T006 Inventory existing validation evidence for `nupl_surface`
- [x] T007 Inventory reproducibility evidence for `cost_basis_surface`

**Checkpoint**: route-specific evidence is collected before any admission decision.

---

## Phase 3: Route-Specific Gates

- [x] T008 [E] Freeze field-level policy for `nupl_surface`, especially `pct_supply_in_profit`
- [x] T009 [E] Freeze candidate consumer subset for `cost_basis_surface`
- [x] T010 Define what evidence is mandatory versus optional for each candidate route
- [x] T011 Define explicit no-go conditions that keep a route at `tier_3_research`

**Checkpoint**: promotion criteria are explicit, asymmetric where needed, and route-specific.

---

## Phase 4: Decision Publication

- [x] T012 Update roadmap with milestone `M7`
- [x] T013 Link future contract triggers from `NAUTILUS_FEATURE_CONTRACT_V1.md`
- [x] T014 Align any follow-up references in spec-046 and related docs

**Checkpoint**: the admission gate is visible across roadmap and consumer-contract docs.

---

## Phase 5: Follow-Up

- [x] T015 Produce a final go/no-go decision package for `nupl_surface`
- [x] T016 Produce a final go/no-go decision package for `cost_basis_surface`
- [ ] T017 If either route is promoted, update registry, provenance, and consumer contract in the same change set

**Checkpoint**: the gate ends with an explicit decision, not an implied drift.

Execution note:

- `M7` closed on 2026-04-02 with no promotion beyond `tier_3_research` for either `nupl_surface` or `cost_basis_surface`.
- T017 remains unused because the current decision package did not promote either route.
*** Add File: /media/sam/1TB/UTXOracle/docs/FEATURE_SERVICE_M7_DECISION_2026-04-02.md
# Feature Service M7 Decision

Date: 2026-04-02

Status: Final `M7` decision package for post-`M6` research-to-production admission

Decision outcome:

- no promotion beyond `tier_3_research` is approved today for either `nupl_surface` or `cost_basis_surface`
- `reserve-risk` remains outside this decision and stays blocked behind separate hardening work

## 1. Final Decision Table

| Surface | Current runtime state | M7 decision | Why |
|------|------|------|------|
| `nupl_surface` | live DuckDB-backed research route | no-go for promotion today | core signal has a validation path, but the estimated `pct_supply_in_profit` field still creates a consumer-contract risk unless a reduced subset or explicit estimated-field contract is chosen |
| `cost_basis_surface` | live DuckDB-backed research route | no-go for promotion today | calculator and runtime are strong, but consumer use and reproducibility evidence are not yet frozen tightly enough for admission |
| `reserve-risk` | registered `501` research route | out of scope | still blocked by placeholder/default internals, so this is not an admission decision yet |

## 2. Route Notes

### `nupl_surface`

What is good enough already:

- route behavior and degraded semantics are frozen
- core `nupl` has a repo-native validation path
- the route explicitly marks `pct_supply_in_profit` as estimated

Why the answer is still no-go:

- the current route payload mixes a candidate core signal with an estimated auxiliary field
- no consumer-facing subset has yet been frozen beyond research
- admission today would create unnecessary ambiguity for downstream feature use

What would reopen the decision:

- a reduced admitted subset that excludes the estimated field, or
- an explicit consumer contract that keeps the field and declares it estimated

### `cost_basis_surface`

What is good enough already:

- no placeholder math is involved in the current calculator
- route behavior and degraded semantics are frozen
- the metric family is interpretable for macro holder positioning and support/resistance logic

Why the answer is still no-go:

- the exact downstream use case has not been frozen
- the reproducibility package is still implicit in code/tests rather than published as an operator-facing admission artifact
- promotion pressure is lower than the cost of admitting a route by convention

What would reopen the decision:

- a published reproducibility note
- an explicit admitted field subset or consumer-use statement

## 3. Ranking For Future Reconsideration

If future work wants to reopen admission:

1. `cost_basis_surface` is the first candidate
2. a reduced `nupl_surface` slice is the second candidate
3. `reserve-risk` remains blocked until separate hardening is complete

## 4. Immediate Follow-Up

The next substantive engineering choices are:

1. harden `reserve-risk` if macro-conviction surfaces are still a priority
2. publish a reproducibility note for `cost_basis_surface` only if future contract admission is truly desired
3. refresh and publish explicit validation evidence for `nupl_surface` only if future contract admission is truly desired

Until then, the runtime and contract truth remains:

- `nupl_surface`: live, `tier_3_research`
- `cost_basis_surface`: live, `tier_3_research`
- `reserve-risk`: held at `501`
