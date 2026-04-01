# spec-048: Implementation Plan

## Execution Order

```
Phase 1: RED Trustworthiness Tests
├── add tests proving current mocked or hardcoded behavior
├── add tests proving route shadowing
├── add tests proving duplicate live exposure policy expectations
└── freeze demotion criteria

Phase 2: Route-by-Route Hardening Decisions
├── decide keep-vs-demote for PRO Risk
├── decide keep-vs-demote for Puell Multiple
├── decide canonical live host policy
└── decide technical fix for power-law routing

Phase 3: Implementation
├── wire real PRO Risk inputs or demote route family
├── replace hardcoded Puell baseline or demote route family
├── fix power-law route order conflict
└── enforce live router host policy

Phase 4: Registry and Provenance Update
├── update contract tiers and caveats
├── update backend/provenance manifest entries
└── remove resolved caveat notes from docs where appropriate

Phase 5: Verification
├── run targeted tests for hardened routes
├── verify route tables and host exposure
└── confirm docs and runtime agree
```

## Core Principle

Documentation can describe caveats temporarily. It must not become the long-term substitute for implementation hardening or deliberate demotion.

## Decision Gates

### Gate A: Keep vs Demote

Before spending implementation effort, confirm whether each route family:

1. belongs in the admitted contract
2. has real consumer value
3. has a credible path to trustworthy inputs

### Gate B: Routing Fix

Before accepting any route-order workaround, confirm:

1. the specific route wins deterministically
2. generic routes still behave as intended
3. tests lock the behavior

### Gate C: Live Host Policy

Before keeping dual exposure, confirm:

1. both hosts are intentionally supported
2. lifecycle assumptions match
3. the contract registry reflects dual-host policy

If not, one host must be canonical and the other demoted or removed.

## Estimated Effort

| Area | Effort | Notes |
|------|--------|-------|
| trustworthiness tests and decisions | 0.5-1 day | high signal |
| PRO Risk hardening or demotion | 1-2 days | depends on data availability |
| Puell hardening or demotion | 0.5-1.5 days | denominator source is the key blocker |
| routing and host policy cleanup | 0.5-1 day | straightforward once decided |
| **Total** | **2.5-5.5 days** | depends on keep-vs-demote choices |

