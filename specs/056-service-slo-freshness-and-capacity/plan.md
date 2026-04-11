# spec-056: Implementation Plan

## Execution Order

```
Phase 1: SLO Scope Freeze
├── freeze which surfaces get strict SLOs
├── freeze the local single-host deployment assumption
├── separate internal SLO from external SLA language
└── freeze which metrics matter for execution use

Phase 2: Freshness Model
├── freeze freshness classes
├── freeze healthy/degraded/stale thresholds
├── align route-level semantics across tier-1 surfaces
└── define which threshold transitions block trading

Phase 3: Latency and Availability Targets
├── set p95 targets for tier-1 latest reads
├── set bounded history targets
├── set availability targets
└── define which violations are operator-visible versus execution-critical

Phase 4: Capacity Assumption
├── freeze the intended consumer model
├── define burst and retry assumptions
├── decide what load is explicitly out of scope
└── align the capacity story with the actual host topology

Phase 5: Governance and Telemetry Alignment
├── publish one canonical SLO artifact
├── connect thresholds to execution-state logic
├── connect thresholds to alerts and incidents
└── align docs and runbooks
```

## Core Principle

The service does not need internet-scale promises. It needs explicit local execution-grade numbers that tell the operator and `NT` when the service is still trustworthy.

## Decision Gates

### Gate A: SLO Scope

Before assigning strict SLOs to a surface, confirm:

1. the surface is in `tier_1_execution`
2. the consumer value justifies the promise
3. the data has explicit freshness semantics
4. the measurement is practical on the current host

### Gate B: Freshness Thresholds

Before freezing healthy/degraded/stale thresholds, confirm:

1. the threshold matches real producer cadence
2. the threshold is simple enough for operators to reason about
3. the threshold can feed execution decisions deterministically
4. the threshold is not aspirational noise

### Gate C: Capacity Model

Before publishing capacity assumptions, confirm:

1. the model matches one serious automated consumer
2. operator/debug usage is included realistically
3. out-of-scope load is explicit
4. the stated capacity can be verified locally

## Estimated Effort

| Area | Effort | Notes |
|------|--------|-------|
| SLO and freshness freeze | 1-2 days | mostly design and telemetry mapping |
| capacity assumptions | 0.5-1 day | keep narrow |
| docs and execution coupling | 0.5-1.5 days | should stay compact |
| **Total** | **2-4.5 days** | best done before full execution-state implementation |

