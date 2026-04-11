# Cross-Spec Sync: spec-054 + spec-055 + spec-056 + spec-057 + spec-058 + spec-059

This file tracks the binding couplings inside the execution-grade NT hardening pack:

- [spec-054](/media/sam/1TB/UTXOracle/specs/054-production-boundary-and-surface-tiering/spec.md)
- [spec-055](/media/sam/1TB/UTXOracle/specs/055-nt-execution-safety-contract/spec.md)
- [spec-056](/media/sam/1TB/UTXOracle/specs/056-service-slo-freshness-and-capacity/spec.md)
- [spec-057](/media/sam/1TB/UTXOracle/specs/057-data-quality-reconciliation-and-restatement/spec.md)
- [spec-058](/media/sam/1TB/UTXOracle/specs/058-schema-evolution-and-deprecation-policy/spec.md)
- [spec-059](/media/sam/1TB/UTXOracle/specs/059-observability-and-incident-response/spec.md)

Usage:

- keep one row per real coupling, not per discussion
- update `Resolution` only when both sides are aligned
- use `Locked In` to point to the spec section, decision log row, or implementation artifact that made the coupling concrete

| Coupling | Canonical Owner / Decision Home | Upstream Touchpoint | Downstream Touchpoint | Sync Rule | Resolution | Locked In |
|----------|----------------------------------|---------------------|-----------------------|-----------|------------|-----------|
| execution-eligible surfaces | `spec-054` | route-family tiering and host boundary | `spec-055`, `spec-056`, `spec-059` | only `tier_1_execution` surfaces may drive SLO, execution safety, and canonical telemetry in the first slice | spec-054 freezes the tier list; downstream specs inherit it verbatim and must not invent parallel surface vocabularies | spec-054 decisions.md T006-T017 |
| execution mode state machine | `spec-055` | execution modes, fail-closed rule, operator stages | `spec-056`, `spec-057`, `spec-059` | SLO, data quality, and observability feed the state machine; they do not create parallel execution vocabularies | spec-055 owns the 5-mode vocabulary; spec-056 supplies thresholds, spec-057 supplies quality states, spec-059 supplies evidence — none may introduce execution modes outside this set | spec-055 decisions.md T002, T003 |
| freshness thresholds | `spec-056` | healthy/degraded/stale numeric targets | `spec-055`, `spec-059` | execution gating and freshness alerts must reuse the same thresholds | spec-056 freezes numeric targets (live ≤15s healthy, ≥30s stale; bundle/signal ≤30s healthy, ≥60s stale); spec-055 and spec-059 consume these values, never redefine them | spec-056 decisions.md T007-T010 |
| quarantined and restated data behavior | `spec-057` | quality-state model, restatement semantics | `spec-055`, `spec-059` | quarantined or unresolved critical restated tier-1 data cannot silently remain execution-safe | spec-057 owns the quality vocabulary (`valid`/`suspect`/`quarantined`/`restated`); spec-055 maps `quarantined` → cannot coexist with `trade_enabled`; spec-059 alerts on quarantine/restatement events | spec-057 decisions.md T001-T006, spec-055 spec.md#2-fail-closed-rule |
| schema-change rollout | `spec-058` | additive-only v1 policy, deprecation windows, compatibility gates | `spec-055` | execution-grade route changes, including `behavioral_tightening`, cannot bypass NT compatibility checks | spec-058 freezes change classes, 30-day deprecation window, and compatibility evidence location; spec-055 execution-status route must pass the NT compatibility gate before any schema-affecting change lands | spec-058 decisions.md T011-T015 |
| incident severity and runbooks | `spec-059` | telemetry, alert severity, incident artifacts | `spec-055`, `spec-056`, `spec-057` | runbooks and incidents must reflect the same execution, freshness, and quality rules rather than inventing alternatives or using generic app health as a clearance shortcut | spec-059 owns alert severity (`warning`/`critical`/`fatal`) and runbook set; severity maps to execution via: `warning` → investigate, `critical` → `manage_only` or `halted`, `fatal` → immediate `halted`; clearance requires tier-1 evidence recovery per spec-056 thresholds | spec-059 decisions.md T010, T011, T021 |
