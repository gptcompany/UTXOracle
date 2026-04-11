# spec-058: Implementation Plan

## Execution Order

```
Phase 1: Change-Class Freeze
├── freeze the change vocabulary
├── separate additive from breaking
├── freeze what counts as semantic breakage
└── define the first-slice v1 policy

Phase 2: Deprecation and Versioning Rules
├── define major-version expectations
├── define deprecation windows
├── define emergency override behavior
└── define overlap expectations when practical

Phase 3: Compatibility Gates
├── define route-contract verification
├── define replay compatibility verification
├── define NT adapter compatibility verification
└── define promotion prerequisites for schema-affecting changes

Phase 4: Governance Alignment
├── align contract registry language
├── align provenance references where needed
├── publish operator and consumer guidance
└── make the policy easy to enforce in review
```

## Core Principle

Execution-grade consumers do not just need a contract. They need a stable contract with a narrow and predictable change policy.

## Decision Gates

### Gate A: Additive Versus Breaking

Before classifying a change as non-breaking, confirm:

1. no field is removed or renamed
2. no required field becomes newly required in an incompatible way
3. no existing field changes meaning silently
4. the NT consumer can ignore the change safely

### Gate B: Deprecation Window

Before shortening or bypassing deprecation, confirm:

1. the situation is genuinely urgent
2. the operator impact is understood
3. the consumer migration path is explicit
4. the exception is recorded

### Gate C: Compatibility Gate

Before promoting a schema-affecting change into the execution path, confirm:

1. route contracts pass
2. replay compatibility is verified
3. NT compatibility is verified
4. the change class and rollout path are recorded

## Estimated Effort

| Area | Effort | Notes |
|------|--------|-------|
| change-policy freeze | 0.5-1 day | keep simple |
| deprecation/version rules | 0.5-1 day | narrow and explicit |
| compatibility gating | 1-2 days | highest practical value |
| docs and governance alignment | 0.5-1 day | should be lightweight |
| **Total** | **2.5-5 days** | useful before any future v2 churn |

