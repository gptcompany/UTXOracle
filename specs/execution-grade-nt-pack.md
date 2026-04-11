# Execution-Grade NT Spec Pack

Date: 2026-04-10

Status: Draft planning pack for the next service-hardening wave after `spec-052` and `spec-053`

This pack defines the minimum KISS spec set needed to move `UTXOracle` from a strong local feature service into an execution-grade upstream for `Nautilus Trader` with real capital.

Included specs:

- [spec-054](/media/sam/1TB/UTXOracle/specs/054-production-boundary-and-surface-tiering/spec.md)
- [spec-055](/media/sam/1TB/UTXOracle/specs/055-nt-execution-safety-contract/spec.md)
- [spec-056](/media/sam/1TB/UTXOracle/specs/056-service-slo-freshness-and-capacity/spec.md)
- [spec-057](/media/sam/1TB/UTXOracle/specs/057-data-quality-reconciliation-and-restatement/spec.md)
- [spec-058](/media/sam/1TB/UTXOracle/specs/058-schema-evolution-and-deprecation-policy/spec.md)
- [spec-059](/media/sam/1TB/UTXOracle/specs/059-observability-and-incident-response/spec.md)

Pack sync file:

- [execution-grade-nt-cross-spec-sync.md](/media/sam/1TB/UTXOracle/specs/execution-grade-nt-cross-spec-sync.md)

## Why This Pack Exists

The current repo is already strong in feature-service terms:

- canonical `:8011` live service
- frozen contract and provenance layers
- bounded BTC bundles and signal snapshots
- entity and flow foundations

What is still missing for real-capital `NT` usage is not more feature breadth. The missing layer is execution-grade service governance.

## Ordering

Recommended implementation order:

1. `spec-054`
   freeze the boundary and the execution-eligible surfaces
2. `spec-055`
   define the final execution state machine and fail-closed rules
3. `spec-056`
   freeze numeric freshness and latency targets
4. `spec-057`
   freeze data-quality, quarantine, and restatement rules
5. `spec-058`
   freeze change discipline so `NT` cannot break silently
6. `spec-059`
   wire the telemetry, alerts, and incident runbooks that support the execution contract

## Guiding Rule

The pack is intentionally narrow:

- single operator
- local or private deployment
- one serious automated consumer
- fail-closed over broad exposure

It does not assume:

- multi-tenant SaaS
- billing
- enterprise org structure
- public API scale

## Final Outcome

When this pack is complete, `UTXOracle` should be able to answer one hard question cleanly:

`Is this service allowed to influence live capital in NT right now?`

That is the standard the pack is designed to satisfy.
