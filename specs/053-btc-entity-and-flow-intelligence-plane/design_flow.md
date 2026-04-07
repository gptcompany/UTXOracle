# Design: Mapping Pipeline and Flow Model

Date: 2026-04-07
Spec: spec-053

## 1. Mapping Pipeline (Cluster to Entity)

The pipeline transforms raw `address_clusters` into a governed `entity_registry`.

### 1.1 Ingestion Rules
- **Cluster to Registry**: Every unique `cluster_id` from local union-find becomes a candidate entity `btc:entity:cluster:<cluster_id>`.
- **Label Propagation**: If a cluster has a label in DuckDB, it populates `entity_labels` with `label_kind='inherited'` and `review_status='unreviewed'`.
- **Curated Overrides**: Manual CSV/YAML hints (e.g., `exchange_addresses.csv`) override heuristic labels. If a curated label matches multiple clusters, those clusters are mapped to a single `entity_id` (e.g., `btc:entity:curated:binance`).
- **Reconciliation**:
    - Disagreement between heuristics: Use the one with higher component confidence.
    - Disagreement with manual curated data: Curated data always wins.
    - Multiple curated sources: Newest timestamp wins unless marked as `primary`.

## 2. Flow Model (Movement and Aggregates)

The flow model tracks how BTC moves between entities.

### 2.1 Event Layer
- **`entity_movement_events`**: 1:1 mapping with blockchain transactions that cross cluster/entity boundaries.
    - Fields: `txid`, `ts`, `source_entity_id`, `target_entity_id`, `btc_amount`, `classification`, `confidence`.
- **`entity_transfer_edges`**: Directional links derived from events.
    - Note: A single transaction might be decomposed into multiple edges if it involves multiple source/target entities.

### 2.2 Aggregate Layer
- **`entity_flows_daily`**: Daily Inflow/Outflow/Netflow per entity.
- **`entity_balance_snapshots_daily`**: End-of-day estimated balance per entity (sum of cluster unspent).
- **`entity_counterparty_edges_daily`**: Daily sum of volume between entity pairs.

### 2.3 Classification Rules (Internal vs External)
- **Internal Reshuffle**: If `source_entity_id == target_entity_id`, classify as `internal_entity_reshuffle`.
    - This includes movements between different clusters that have been mapped to the same entity.
- **External Flow**: If `source_entity_id != target_entity_id`.
- **Ambiguous**: If source or destination cluster cannot be resolved to a single entity with > 0.5 confidence.

## 3. Heuristic Safeguards
- Do not treat change outputs as external flow.
- Do not treat CoinJoin participants as a single entity unless the coordinator is the target.
- Do not treat exchange "internal" sweeps as external inflow.
