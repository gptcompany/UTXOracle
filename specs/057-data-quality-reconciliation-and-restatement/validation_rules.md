# Validation and Reconciliation Rules

This document defines the specific checks for tier-1 execution inputs and handling of cross-source reconciliation as defined in Phase 2 of spec-057.

## 1. Validation Layers

### Ingest Validation (T007)
Before tier-1 inputs are written to storage or materialized into bundles, they must pass:
- **Type correctness**: All numeric fields are numbers, timestamps are valid UNIX or ISO8601 strings.
- **Range checks**: Impossible values (e.g., negative BTC prices, negative supply, or values orders of magnitude off baseline) are rejected.
- **Completeness**: No required execution-relevant fields are null or missing.

### Materialization Validation (T008)
When bundles and signals are written to the persistence layer:
- **Structural integrity**: The output bundle strictly adheres to the schema expected by the consumer.
- **Immutability check**: No silent overwrites of already materialized tier-1 data are permitted; mutations must go through the restatement flow.

### Serve-Time Validation (T009)
When the service reads `latest` or `history` data to serve to the NT execution client:
- **Freshness checks**: Data age must be evaluated against the SLO limits defined in spec-056. Stale data must fail closed.
- **Integrity bounds**: Responses must precisely match requested time ranges without returning partial intervals or padded gaps.
- **Quality State filtering**: Data marked as `quarantined` or with unresolved critical `restated` artifacts must not be returned as valid for execution.

### Continuity Checks (T010)
To ensure temporal and sequence integrity:
- **Monotonic timestamps**: Time progression must be strictly forward; out-of-order `latest` readings must escalate to `suspect` or `quarantined`.
- **Sequence consistency**: Bundle and signal sequence IDs must not skip or repeat numbers unexpectedly.

## 2. Reconciliation Rules

### Cross-Source Reconciliation (T011)
Where multiple independent sources or parallel calculations exist:
- Compare the incoming values against alternate streams.
- Statistically significant deviations (exceeding defined % thresholds for the specific metric) must automatically flag the resulting artifact as `suspect`.

### Source-of-Truth-Aware Handling (T012)
Reconciliation logic must adhere to `METRIC_SOURCE_OF_TRUTH_MANIFEST.md`:
- For metrics defined as `local_canonical`, external source disagreement serves only as a reference telemetry signal and does not automatically degrade the local metric to `suspect`.
- For metrics defined as `adopt_from_brk` (or owned by a specific upstream), significant divergence from that canonical upstream directly proves corruption and escalates the metric state to `suspect` or `quarantined`.
