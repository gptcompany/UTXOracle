# Design: Entity Registry and Confidence Model

Date: 2026-04-07
Spec: spec-053

## 1. Schema Design (Authoritative Local Storage)

The authoritative registry is stored in DuckDB (for cluster-derived automated rows) and curated CSV/YAML (for manual overrides).

### 1.1 `entity_registry`
| Field | Type | Description |
|-------|------|-------------|
| `entity_id` | STRING (PK) | `btc:entity:<namespace>:<stable_id>` |
| `entity_kind` | ENUM | exchange, miner, custodian, fund, service, unknown |
| `registry_status` | ENUM | active, candidate, deprecated |
| `display_label` | STRING | Preferred primary label for UI/API |
| `confidence_overall` | DOUBLE | 0.0 - 1.0 (conservative composition) |
| `first_seen` | TIMESTAMP | Earliest evidence of this entity |
| `last_seen` | TIMESTAMP | Latest evidence update |

### 1.2 `cluster_entity_map`
| Field | Type | Description |
|-------|------|-------------|
| `cluster_id` | STRING | Local union-find cluster identifier |
| `entity_id` | STRING | Canonical entity identifier |
| `mapping_confidence` | DOUBLE | Confidence in this cluster belonging to this entity |
| `mapping_method` | STRING | Heuristic name or curation source |
| `mapping_version` | STRING | Version of the mapping logic |

### 1.3 `entity_labels`
| Field | Type | Description |
|-------|------|-------------|
| `entity_id` | STRING | Foreign key to entity_registry |
| `label` | STRING | Human-readable name (e.g., "Binance") |
| `label_kind` | ENUM | primary, alias, internal |
| `label_confidence` | DOUBLE | Confidence in this specific label |
| `is_primary` | BOOLEAN | If true, used for display_label |

### 1.4 `entity_label_provenance`
| Field | Type | Description |
|-------|------|-------------|
| `entity_id` | STRING | |
| `label` | STRING | |
| `source_kind` | ENUM | heuristic, curated_csv, manual, external, inherited |
| `source_name` | STRING | e.g., "exchange_addresses.csv", "mempool_api" |
| `source_ref` | STRING | URL, file hash, or transaction ID |
| `review_status` | ENUM | unreviewed, provisional, reviewed, deprecated |
| `method_version` | STRING | |

## 2. Confidence Composition Rules

### 2.1 First-Slice Rule (Conservative)
The overall confidence is the product of component confidences, emphasizing that any weak link reduces the total certainty.

`confidence_overall = cluster_confidence * mapping_confidence * label_confidence`

Where:
- `cluster_confidence`: Reliability of the address clustering (defaults to 0.9 for MIH, 0.7 for CAH).
- `mapping_confidence`: Reliability of the cluster-to-entity link (defaults to 1.0 for direct curated matches).
- `label_confidence`: Reliability of the label source (defaults to 1.0 for curated, 0.8 for high-confidence heuristics).

### 2.2 Downgrade Behavior
- **Conflict**: If two distinct labels with high confidence are assigned to the same entity without a clear primary, `registry_status` moves to `candidate` and `confidence_overall` is penalized by 50%.
- **Staleness**: If `last_seen` is > 30 days old, `confidence_overall` degrades by 10% weekly until a 0.5 floor.
- **Ambiguity**: If a cluster splits (rare in union-find but possible if a previously merged input is re-evaluated), related mappings are marked `provisional`.

## 3. Serving Materialization (QuestDB)

Materialized copies in QuestDB will collapse these for fast lookup:
- `entity_registry_serving`: Collapsed view of registry + primary labels.
- `entity_provenance_serving`: Collapsed JSON summary of evidence for API exposure.
