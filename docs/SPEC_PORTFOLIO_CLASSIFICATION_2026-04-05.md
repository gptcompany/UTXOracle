# Spec Portfolio Classification

Date: 2026-04-05

Status: Current portfolio classification after source-of-truth realignment, whale/entity closure pass, and legacy backlog triage

Purpose:

- classify the remaining and recently touched specs as `Closed`, `Dormant`, `Maintenance`, or `Active`
- distinguish real operational ownership from stale checklist debt
- keep future scope decisions aligned with [docs/SCOPE_LOCK_2026-04-02.md](/media/sam/1TB/UTXOracle/docs/SCOPE_LOCK_2026-04-02.md)

## Label Meanings

- `Closed`: the spec delivered its intended scope and no meaningful active backlog remains inside it
- `Dormant`: the spec is not the active roadmap and should only reopen through an explicit follow-up decision
- `Maintenance`: the spec is not primary roadmap, but it still owns limited operational, validation, or upstream-follow-up work
- `Active`: current implementation roadmap; should be rare under the present scope lock

## Current Classification

| Spec | Label | Open tasks | Current interpretation |
|------|------|------|------|
| `spec-002` | `Dormant` | `0` | earlier mempool-live prototype line; superseded by the canonical `:8011` live stack and closed administratively as backlog noise |
| `spec-003` | `Maintenance` | `0` | legacy batch/comparison path remains maintained, but the remaining reboot/resource drills were deferred as operator validations rather than active repository backlog |
| `spec-004` | `Closed` | `0` | whale-flow detection foundation delivered; later whale/entity work builds on it without leaving active checklist debt here |
| `spec-005` | `Closed` | `0` | mempool whale realtime foundation delivered; later canonical whale work moved to the unified `:8011` surface |
| `spec-006` | `Dormant` | `83` | old whale dashboard plan, not aligned with the current canonical whale/entity surface and not part of the present roadmap |
| `spec-007` | `Closed` | `0` | core on-chain metrics implementation delivered with no remaining active checklist debt |
| `spec-008` | `Closed` | `0` | derivatives historical slice delivered with no remaining active checklist debt |
| `spec-009` | `Closed` | `0` | advanced on-chain analytics slice delivered with no remaining active checklist debt |
| `spec-010` | `Closed` | `0` | Wasserstein metric slice delivered with no remaining active checklist debt |
| `spec-011` | `Closed` | `0` | alert-system implementation delivered with no remaining active checklist debt |
| `spec-012` | `Closed` | `0` | backtesting framework implementation delivered with no remaining active checklist debt |
| `spec-013` | `Closed` | `0` | clustering/CoinJoin foundation delivered; `address_clusters` remains local and active, but Phase 9 residual work was closed administratively |
| `spec-014` | `Closed` | `0` | evidence-based weighting slice delivered with no remaining active checklist debt |
| `spec-015` | `Dormant` | `3` | residual finalization/report-publication checklist only; not current roadmap work |
| `spec-016` | `Closed` | `0` | SOPR implementation slice delivered with no remaining active checklist debt |
| `spec-017` | `Closed` | `0` | UTXO lifecycle engine delivered with no remaining active checklist debt |
| `spec-018` | `Maintenance` | `3` | cointime implementation is shipped, but external validation fixture/benchmark follow-up still remains |
| `spec-019` | `Closed` | `0` | derivatives weight-adjustment slice delivered with no remaining active checklist debt |
| `spec-020` | `Closed` | `0` | MVRV implementation/refinement slice delivered with no remaining active checklist debt |
| `spec-021` | `Closed` | `0` | advanced on-chain metrics slice delivered with no remaining active checklist debt |
| `spec-022` | `Closed` | `0` | NUPL oscillator implementation delivered; later governance may hold admission, but the implementation spec itself carries no active debt |
| `spec-023` | `Closed` | `0` | cost-basis cohorts implementation delivered; later admission/governance is handled elsewhere |
| `spec-024` | `Closed` | `0` | revived-supply slice delivered with no remaining active checklist debt |
| `spec-025` | `Closed` | `0` | wallet-waves slice delivered; later canonicalization/materialization is tracked by newer specs rather than this implementation checklist |
| `spec-026` | `Closed` | `0` | exchange-netflow slice delivered with no remaining active checklist debt |
| `spec-027` | `Closed` | `0` | binary CDD slice delivered with no remaining active checklist debt |
| `spec-028` | `Closed` | `0` | net realized P/L slice delivered with no remaining active checklist debt |
| `spec-029` | `Closed` | `0` | P/L ratio slice delivered with no remaining active checklist debt |
| `spec-030` | `Closed` | `0` | historical mining/hash-ribbons implementation slice delivered with no remaining active checklist debt |
| `spec-031` | `Closed` | `0` | validation-framework slice delivered with no remaining active checklist debt |
| `spec-032` | `Closed` | `0` | metrics dashboard/chart-page slice delivered with no remaining active checklist debt |
| `spec-033` | `Closed` | `0` | PRO Risk implementation slice delivered; current route admission status is governed elsewhere |
| `spec-034` | `Closed` | `0` | price power-law model slice delivered with no remaining active checklist debt |
| `spec-035` | `Maintenance` | `12` | RBN validation/comparison surface remains useful for formula alignment, reproducibility, and API migration follow-up |
| `spec-036` | `Closed` | `0` | custom price-models framework delivered with no remaining active checklist debt |
| `spec-037` | `Closed` | `0` | database-consolidation slice delivered with no remaining active checklist debt |
| `spec-038` | `Closed` | `0` | exchange-address expansion slice delivered with no remaining active checklist debt |
| `spec-039` | `Closed` | `0` | address-balance-cohorts slice delivered with no remaining active checklist debt |
| `spec-040` | `Closed` | `0` | canonical live service slice completed |
| `spec-041` | `Closed` | `0` | QuestDB operational convergence completed |
| `spec-042` | `Closed` | `0` | charting validation slice completed |
| `spec-043` | `Closed` | `0` | nautilus live trading integration slice completed |
| `spec-044` | `Closed` | `0` | feature contract registry completed and already part of the active governance baseline |
| `spec-045` | `Closed` | `0` | dependency/provenance manifest completed and already part of the active governance baseline |
| `spec-046` | `Closed` | `0` | calculator surface productization completed; post-close regression fix verified |
| `spec-047` | `Closed` | `0` | canonical whale/entity surface foundation completed |
| `spec-048` | `Closed` | `0` | route-hardening bookkeeping realigned; checklist now matches implemented state |
| `spec-049` | `Closed` | `1` | admission gate completed with no promotion; the remaining task is conditional and only activates if a future promotion occurs |
| `spec-050` | `Closed` | `0` | canonical `:8011` promotion completed |
| `spec-051` | `Closed` | `0` | whale entity enrichment operationalization completed; post-close regression fix verified |

## Portfolio Reading Rule

- `Closed` does not mean the underlying code is dead; it means the spec no longer carries active project-management debt.
- `Dormant` specs should not receive opportunistic work just because old tasks exist.
- `Maintenance` specs may still justify small targeted work when that work clearly belongs to their retained ownership area.
- Under the current scope lock, no spec in this classification set should be treated as `Active` unless a new written reopening decision is made.

## Practical Next-Step Rule

- If a new task strengthens the canonical `:8011` contract or whale/entity forensics, open a fresh follow-up spec instead of reviving dormant prototype specs by default.
- If a task only preserves an existing retained path, place it under the relevant `Maintenance` spec.
- If a task does not clearly fit a retained ownership area, it is out of scope by default until explicitly reopened.
