# Feature Service Handoff

Date: 2026-04-02

Purpose:

- compact restart point for the next session

## 1. Current State

- `M1` through `M7` are completed and committed
- the repo now also has a metric-level source-of-truth policy frozen in:
  - [docs/METRIC_SOURCE_OF_TRUTH_MANIFEST.md](/media/sam/1TB/UTXOracle/docs/METRIC_SOURCE_OF_TRUTH_MANIFEST.md)
  - [docs/FEATURE_SERVICE_SOURCE_OF_TRUTH_DECISION_2026-04-02.md](/media/sam/1TB/UTXOracle/docs/FEATURE_SERVICE_SOURCE_OF_TRUTH_DECISION_2026-04-02.md)

## 2. Key Engineering Decision

`BRK` is the preferred source for overlapping shared macro metrics when it already computes and exposes them.

`UTXOracle` should only implement locally when:

- `BRK` does not expose the metric
- the metric is repo-specific
- the local methodology is intentionally different
- the implementation is explicitly research-only

## 3. Current Metric Policy

- `utxoracle_price`: local canonical
- `realized_price_usd`: adopt from `BRK`
- `liveliness`: adopt from `BRK` for shared feature use
- `reserve_risk`: adopt from `BRK`; do not continue local productization by default
- `nupl`: live as `tier_3_research`; future admission still needs explicit `BRK` vs local decision
- `cost_basis`: local canonical DuckDB-backed metric

## 4. Important Reset Performed

The local uncommitted `/api/metrics/reserve-risk` hardening/productization work was discarded on purpose before this handoff.

Reason:

- it was duplication-risk work against a metric already covered by `BRK`
- no written source-of-truth decision justified a second local admitted path

## 5. Repo Status

Documentation changes are currently present for:

- [docs/LIVE_STACK_ROLE_MATRIX.md](/media/sam/1TB/UTXOracle/docs/LIVE_STACK_ROLE_MATRIX.md)
- [docs/FEATURE_DEPENDENCY_MATRIX.md](/media/sam/1TB/UTXOracle/docs/FEATURE_DEPENDENCY_MATRIX.md)
- [docs/FEATURE_SERVICE_ROADMAP_2026-04-01.md](/media/sam/1TB/UTXOracle/docs/FEATURE_SERVICE_ROADMAP_2026-04-01.md)
- [docs/FEATURE_CONTRACT_REGISTRY.md](/media/sam/1TB/UTXOracle/docs/FEATURE_CONTRACT_REGISTRY.md)
- [docs/NAUTILUS_FEATURE_CONTRACT_V1.md](/media/sam/1TB/UTXOracle/docs/NAUTILUS_FEATURE_CONTRACT_V1.md)
- [docs/FEATURE_SERVICE_WAVE2_DECISION_2026-04-02.md](/media/sam/1TB/UTXOracle/docs/FEATURE_SERVICE_WAVE2_DECISION_2026-04-02.md)
- [docs/FEATURE_SERVICE_M7_DECISION_2026-04-02.md](/media/sam/1TB/UTXOracle/docs/FEATURE_SERVICE_M7_DECISION_2026-04-02.md)
- [docs/METRIC_SOURCE_OF_TRUTH_MANIFEST.md](/media/sam/1TB/UTXOracle/docs/METRIC_SOURCE_OF_TRUTH_MANIFEST.md)
- [docs/FEATURE_SERVICE_SOURCE_OF_TRUTH_DECISION_2026-04-02.md](/media/sam/1TB/UTXOracle/docs/FEATURE_SERVICE_SOURCE_OF_TRUTH_DECISION_2026-04-02.md)
- [docs/contracts/feature_contract_registry.yaml](/media/sam/1TB/UTXOracle/docs/contracts/feature_contract_registry.yaml)
- [docs/contracts/metric_source_of_truth_manifest.yaml](/media/sam/1TB/UTXOracle/docs/contracts/metric_source_of_truth_manifest.yaml)
- [specs/046-calculator-surface-productization/spec.md](/media/sam/1TB/UTXOracle/specs/046-calculator-surface-productization/spec.md)
- [specs/046-calculator-surface-productization/tasks.md](/media/sam/1TB/UTXOracle/specs/046-calculator-surface-productization/tasks.md)

## 6. Validation Already Done

- duplicate reserve-risk code changes removed
- YAML parse passed
- `git diff --check` passed

## 7. Next Recommended Step

1. commit the current documentation checkpoint
2. run an external delta review of the source-of-truth policy docs
3. after approval, start Wave 1 history/materialization instead of new overlapping macro metric work

## 8. Do Not Lose

- `BRK` in this stack is a metric-computation service, not just a dashboard
- `electrs` is raw-chain infra, not a metric source-of-truth
- “QuestDB migration complete” does not mean DuckDB disappeared; the repo is still hybrid
- do not reopen `reserve-risk` local productization unless the manifest is intentionally superseded
