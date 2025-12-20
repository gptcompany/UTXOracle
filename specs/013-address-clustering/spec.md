# Feature Specification: Address Clustering & CoinJoin Detection

**Feature Branch**: `013-address-clustering`
**Created**: 2025-12-04
**Status**: Draft
**Prerequisites**: spec-004 (Whale Flow Detection)
**Input**: User description: "Implement address clustering heuristics to identify addresses belonging to the same entity, and CoinJoin detection to filter out privacy-enhanced transactions from whale analysis. This improves whale tracking accuracy by reducing false positives from CoinJoin transactions and better identifying whale entities."

## Context & Motivation

### Background: Entity Resolution

Current whale tracking analyzes individual transactions, but doesn't consider that:

1. **One entity = many addresses**: Whales use multiple addresses for security
2. **CoinJoin creates false signals**: Privacy transactions look like whale movements but aren't
3. **Change outputs mislead**: Change addresses shouldn't count as separate recipients

| Problem | Impact on Whale Tracking | Solution |
|---------|-------------------------|----------|
| Multiple whale addresses | Undercount accumulation | Address clustering |
| CoinJoin transactions | False whale signals | CoinJoin detection |
| Change output confusion | Inflated recipient count | Change heuristics |

**Expected Accuracy Gain**: +10-15% whale detection precision (from literature)

### Scientific Foundation

**Address Clustering Heuristics**:

1. **Multi-Input Heuristic (MIH)**: If inputs A and B are in same transaction, A and B belong to same entity
   - Most reliable heuristic
   - Works because only owner can sign all inputs

2. **Change Address Heuristic (CAH)**: Output going back to input's entity is change
   - Detects: round amounts (likely payment), odd amounts (likely change)
   - Used to extend MIH clusters

3. **Address Reuse Detection**: Same address used multiple times = same entity (trivial but useful)

**CoinJoin Detection Heuristics**:

1. **Equal Output Amounts**: CoinJoin mixes use identical output values (e.g., all 0.1 BTC)
2. **Many Inputs/Outputs**: CoinJoin typically has 5+ inputs AND 5+ outputs
3. **No Address Reuse**: CoinJoin participants rarely reuse addresses
4. **Known CoinJoin Patterns**: Wasabi (coordinator), JoinMarket (maker/taker), Whirlpool (pools)

**Reference**: Meiklejohn et al. (2013) "A Fistful of Bitcoins: Characterizing Payments Among Men with No Names"

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Multi-Input Clustering (Priority: P1)

As a Bitcoin analyst, I want to **cluster addresses that appear together in transaction inputs**, so I can identify all addresses belonging to the same entity.

**Why this priority**: Foundation for entity-level analysis. Multi-input heuristic is most reliable and essential. ~100 LOC.

**Independent Test**: Can be fully tested by:
1. Providing transaction with inputs from addresses A, B, C
2. Running clustering algorithm
3. Verifying A, B, C are in same cluster

**Acceptance Scenarios**:

1. **Given** transaction with inputs from addresses A, B
   **When** multi-input clustering runs
   **Then** A and B are assigned same cluster_id

2. **Given** transaction 1: inputs A, B and transaction 2: inputs B, C
   **When** multi-input clustering runs on both
   **Then** A, B, C all have same cluster_id (transitivity)

3. **Given** 1000 transactions with overlapping inputs
   **When** clustering completes
   **Then** returns cluster assignments for all unique addresses

4. **Given** transaction with single input
   **When** clustering runs
   **Then** address assigned unique cluster (no merge)

---

### User Story 2 - CoinJoin Detection (Priority: P1)

As a Bitcoin analyst, I want to **identify CoinJoin transactions**, so I can exclude them from whale movement analysis.

**Why this priority**: CoinJoin creates massive false positives in whale detection. Must filter. ~80 LOC.

**Independent Test**: Can be fully tested by:
1. Providing known CoinJoin transaction structure
2. Running CoinJoin detector
3. Verifying detection rate > 90%

**Acceptance Scenarios**:

1. **Given** transaction with 5 inputs and 5 equal outputs (0.1 BTC each)
   **When** CoinJoin detector runs
   **Then** is_coinjoin=True, confidence > 0.9

2. **Given** normal transaction with 2 inputs, 2 different outputs
   **When** CoinJoin detector runs
   **Then** is_coinjoin=False

3. **Given** Wasabi CoinJoin (coordinator pattern, 100+ outputs)
   **When** CoinJoin detector runs
   **Then** is_coinjoin=True, coinjoin_type="wasabi"

4. **Given** JoinMarket transaction (maker/taker pattern)
   **When** CoinJoin detector runs
   **Then** is_coinjoin=True, coinjoin_type="joinmarket"

5. **Given** Whirlpool transaction (fixed denomination pools)
   **When** CoinJoin detector runs
   **Then** is_coinjoin=True, coinjoin_type="whirlpool"

---

### User Story 3 - Change Output Detection (Priority: P2)

As a Bitcoin analyst, I want to **identify change outputs**, so I can distinguish real payments from internal transfers.

**Why this priority**: Improves recipient counting and flow direction accuracy. ~60 LOC.

**Independent Test**: Can be fully tested by:
1. Providing transaction with typical payment + change pattern
2. Running change detector
3. Verifying change output identified

**Acceptance Scenarios**:

1. **Given** transaction: input 1.5 BTC → outputs 1.0 BTC + 0.4999 BTC (+ fee)
   **When** change detector runs
   **Then** 0.4999 BTC marked as likely_change=True (odd amount)

2. **Given** transaction: input 2.0 BTC → outputs 1.5 BTC + 0.5 BTC
   **When** change detector runs
   **Then** ambiguous (both round), likely_change=uncertain for smaller

3. **Given** output address matches input address pattern (same prefix)
   **When** change detector runs with script analysis
   **Then** likely_change=True (address reuse pattern)

---

### User Story 4 - Integration with Whale Tracking (Priority: P1)

As a Bitcoin trader, I want **whale detection to use clustering and CoinJoin filtering**, so signals are more accurate.

**Why this priority**: The whole point - improved whale signal quality. ~50 LOC integration.

**Independent Test**: Can be fully tested by:
1. Running whale detection with clustering enabled
2. Comparing results with/without clustering
3. Verifying precision improvement

**Acceptance Scenarios**:

1. **Given** whale threshold 100 BTC, and entity has 50+60 BTC across 2 addresses
   **When** whale detection runs WITH clustering
   **Then** entity detected as whale (110 BTC total)

2. **Given** same scenario WITHOUT clustering
   **When** whale detection runs
   **Then** neither address detected as whale (50 < 100, 60 < 100)

3. **Given** CoinJoin transaction moving 500 BTC
   **When** whale detection runs WITH CoinJoin filter
   **Then** transaction excluded from whale analysis

4. **Given** same CoinJoin WITHOUT filter
   **When** whale detection runs
   **Then** false whale signal generated (incorrect)

---

### Edge Cases

- **What happens when clustering creates very large clusters?**
  → Cap cluster size at 10,000 addresses; flag as "exchange_likely" if exceeded.

- **What happens when CoinJoin detection is uncertain?**
  → Return confidence score; only filter if confidence > 0.8.

- **What happens when address has no transaction history?**
  → Assign unique cluster; will merge when more data available.

- **What happens when entity uses non-standard scripts?**
  → Fall back to output value heuristics only; log for manual review.

---

## Requirements *(mandatory)*

### Functional Requirements

**Address Clustering**:
- **FR-001**: Clustering MUST implement multi-input heuristic (MIH)
- **FR-002**: Clustering MUST support transitive closure (A-B, B-C → A-B-C same cluster)
- **FR-003**: Clustering MUST use Union-Find data structure for efficiency
- **FR-004**: Clustering MUST persist cluster assignments in DuckDB

**CoinJoin Detection**:
- **FR-005**: CoinJoin detector MUST detect equal-output transactions (>3 equal outputs)
- **FR-006**: CoinJoin detector MUST detect high input/output count (>5 each)
- **FR-007**: CoinJoin detector MUST identify Wasabi coordinator pattern
- **FR-008**: CoinJoin detector MUST identify Whirlpool fixed denominations (0.001, 0.01, 0.05, 0.5 BTC)
- **FR-009**: CoinJoin detector MUST return confidence score (0.0-1.0)

**Change Detection**:
- **FR-010**: Change detector MUST flag odd-amount outputs as likely change
- **FR-011**: Change detector MUST flag outputs < 10% of total as likely change
- **FR-012**: Change detector MUST NOT flag all outputs as change (at least one payment)

**Integration**:
- **FR-013**: Whale detection MUST aggregate flows by cluster_id when clustering enabled
- **FR-014**: Whale detection MUST exclude CoinJoin transactions when filtering enabled
- **FR-015**: Configuration: CLUSTERING_ENABLED, COINJOIN_FILTER_ENABLED (both default True)

### Non-Functional Requirements

- **NFR-001**: Clustering 10,000 transactions MUST complete in <10 seconds
- **NFR-002**: CoinJoin detection per transaction MUST complete in <10ms
- **NFR-003**: Pure Python implementation (no graph databases required)
- **NFR-004**: Incremental clustering (new transactions merge into existing clusters)

### Key Entities *(mandatory)*

```python
@dataclass
class AddressCluster:
    cluster_id: str                   # UUID or hash-based ID
    addresses: set[str]               # All addresses in cluster
    total_balance: float              # Sum of balances (if tracked)
    tx_count: int                     # Number of transactions
    first_seen: datetime              # Earliest transaction
    last_seen: datetime               # Latest transaction
    is_exchange_likely: bool          # True if cluster too large (>10k addresses)
    label: str | None                 # Known entity label if identified

@dataclass
class CoinJoinResult:
    txid: str                         # Transaction ID
    is_coinjoin: bool                 # Detection result
    confidence: float                 # 0.0-1.0 confidence
    coinjoin_type: str | None         # "wasabi" | "joinmarket" | "whirlpool" | "generic" | None
    equal_output_count: int           # Number of equal-value outputs
    total_inputs: int                 # Input count
    total_outputs: int                # Output count
    detection_reasons: list[str]      # Why flagged as CoinJoin

@dataclass
class ChangeDetectionResult:
    txid: str                         # Transaction ID
    outputs: list[dict]               # List of {vout, value, is_change, confidence}
    likely_payment_outputs: list[int] # vout indices of likely payments
    likely_change_outputs: list[int]  # vout indices of likely change

@dataclass
class ClusteringStats:
    total_addresses: int              # Unique addresses processed
    total_clusters: int               # Number of clusters
    largest_cluster_size: int         # Addresses in largest cluster
    avg_cluster_size: float           # Average addresses per cluster
    singleton_count: int              # Clusters with single address
    exchange_flagged_count: int       # Clusters flagged as likely exchange
```

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Multi-input clustering correctly groups 95%+ of related addresses
- **SC-002**: CoinJoin detection precision > 90% (few false positives)
- **SC-003**: CoinJoin detection recall > 80% (catches most CoinJoins)
- **SC-004**: Whale detection precision improves by >10% with clustering enabled
- **SC-005**: Clustering 10,000 transactions completes in <10 seconds
- **SC-006**: Code coverage for clustering module ≥85%

### Definition of Done

- [ ] Multi-input heuristic clustering with Union-Find
- [ ] CoinJoin detection for generic, Wasabi, JoinMarket, Whirlpool
- [ ] Change output detection
- [ ] Integration with whale_flow_detector.py
- [ ] DuckDB tables: address_clusters, coinjoin_cache
- [ ] Configuration flags for enabling/disabling features
- [ ] Unit tests (≥85% coverage)
- [ ] Integration test: whale detection with clustering
- [ ] Performance validated (<10s for 10k transactions)
- [ ] Documentation updated

---

## Technical Notes

### Implementation Order (KISS)

1. **Union-Find** (~50 LOC) - Efficient disjoint set data structure
2. **Multi-Input Clustering** (~60 LOC) - Core clustering logic
3. **CoinJoin Detection** (~100 LOC) - Pattern matching
4. **Change Detection** (~50 LOC) - Heuristic analysis
5. **Integration** (~40 LOC) - Hook into whale detector

### Files to Create

- `scripts/clustering/union_find.py` - Union-Find data structure
- `scripts/clustering/address_clustering.py` - Clustering algorithm
- `scripts/clustering/coinjoin_detector.py` - CoinJoin pattern matching
- `scripts/clustering/change_detector.py` - Change output heuristics
- `scripts/clustering/__init__.py` - Public API
- `tests/test_clustering.py` - Test suite

### Files to Modify

- `scripts/whale_flow_detector.py` - Integrate clustering and CoinJoin filter
- `scripts/init_metrics_db.py` - Add clustering tables

### Algorithm: Union-Find (Disjoint Set)

```python
class UnionFind:
    """
    Efficient Union-Find with path compression and union by rank.
    O(α(n)) amortized per operation where α is inverse Ackermann.
    """
    def __init__(self):
        self.parent = {}
        self.rank = {}

    def find(self, x: str) -> str:
        """Find root of x with path compression."""
        if x not in self.parent:
            self.parent[x] = x
            self.rank[x] = 0
            return x

        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])  # Path compression
        return self.parent[x]

    def union(self, x: str, y: str) -> None:
        """Union sets containing x and y by rank."""
        px, py = self.find(x), self.find(y)
        if px == py:
            return

        # Union by rank
        if self.rank[px] < self.rank[py]:
            px, py = py, px
        self.parent[py] = px
        if self.rank[px] == self.rank[py]:
            self.rank[px] += 1

    def connected(self, x: str, y: str) -> bool:
        """Check if x and y are in same cluster."""
        return self.find(x) == self.find(y)

    def get_clusters(self) -> dict[str, set[str]]:
        """Return all clusters as {root: {members}}."""
        clusters = {}
        for addr in self.parent:
            root = self.find(addr)
            if root not in clusters:
                clusters[root] = set()
            clusters[root].add(addr)
        return clusters
```

### Algorithm: CoinJoin Detection

```python
def detect_coinjoin(tx: dict) -> CoinJoinResult:
    """
    Detect if transaction is likely a CoinJoin.

    Heuristics:
    1. Many equal outputs (>3 same value)
    2. High input/output count (>5 each)
    3. Known denomination patterns (Wasabi, Whirlpool)
    """
    inputs = tx.get("vin", [])
    outputs = tx.get("vout", [])

    reasons = []
    confidence = 0.0

    # Count output values
    output_values = [o["value"] for o in outputs]
    value_counts = {}
    for v in output_values:
        v_rounded = round(v, 8)
        value_counts[v_rounded] = value_counts.get(v_rounded, 0) + 1

    max_equal_count = max(value_counts.values()) if value_counts else 0

    # Heuristic 1: Equal outputs
    if max_equal_count >= 3:
        reasons.append(f"equal_outputs:{max_equal_count}")
        confidence += 0.3

    # Heuristic 2: Many inputs/outputs
    if len(inputs) >= 5 and len(outputs) >= 5:
        reasons.append(f"many_io:{len(inputs)}in/{len(outputs)}out")
        confidence += 0.3

    # Heuristic 3: Known denominations (Whirlpool)
    WHIRLPOOL_DENOMS = {0.001, 0.01, 0.05, 0.5}
    if any(round(v, 3) in WHIRLPOOL_DENOMS for v in output_values):
        if max_equal_count >= 5:
            reasons.append("whirlpool_pattern")
            confidence += 0.3

    # Heuristic 4: Wasabi pattern (100+ outputs, coordinator)
    if len(outputs) >= 100:
        reasons.append("wasabi_likely")
        confidence += 0.2

    is_coinjoin = confidence >= 0.5
    coinjoin_type = _classify_coinjoin_type(reasons) if is_coinjoin else None

    return CoinJoinResult(
        txid=tx.get("txid", ""),
        is_coinjoin=is_coinjoin,
        confidence=min(confidence, 1.0),
        coinjoin_type=coinjoin_type,
        equal_output_count=max_equal_count,
        total_inputs=len(inputs),
        total_outputs=len(outputs),
        detection_reasons=reasons,
    )
```

### DuckDB Schema Extension

```sql
-- Add to scripts/init_metrics_db.py
CREATE TABLE IF NOT EXISTS address_clusters (
    address VARCHAR PRIMARY KEY,
    cluster_id VARCHAR NOT NULL,
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    is_exchange_likely BOOLEAN DEFAULT FALSE,
    label VARCHAR
);

CREATE TABLE IF NOT EXISTS coinjoin_cache (
    txid VARCHAR PRIMARY KEY,
    is_coinjoin BOOLEAN NOT NULL,
    confidence DOUBLE,
    coinjoin_type VARCHAR,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_cluster_id ON address_clusters(cluster_id);
CREATE INDEX idx_coinjoin_type ON coinjoin_cache(coinjoin_type);
```

### Configuration

```bash
# .env additions
CLUSTERING_ENABLED=true
COINJOIN_FILTER_ENABLED=true
COINJOIN_CONFIDENCE_THRESHOLD=0.8
MAX_CLUSTER_SIZE=10000
CHANGE_DETECTION_ENABLED=true
```

### Dependencies

- **Internal**: whale_flow_detector.py, DuckDB
- **External**: None (pure Python)
- **Data**: Transaction data from electrs/mempool.space API

### Known CoinJoin Patterns

| Protocol | Pattern | Detection |
|----------|---------|-----------|
| **Wasabi** | Coordinator, 100+ outputs, equal amounts | Large output count + equal values |
| **JoinMarket** | Maker/taker, variable sizes | Multiple equal outputs + specific amounts |
| **Whirlpool** | Fixed pools (0.001, 0.01, 0.05, 0.5 BTC) | Known denominations + equal counts |
| **Generic** | Equal outputs, many participants | >3 equal outputs + >5 inputs |

---

### User Story 5 - Wallet-Level Cost Basis (Priority: P1)

As a Bitcoin analyst, I want to **track acquisition prices at the wallet level**, so that Realized Cap and NUPL calculations match industry standards (CheckOnChain/Glassnode).

**Why this priority**: Current UTXO-level cost basis inflates Realized Cap by 1.8x, causing 36% NUPL deviation. CRITICAL for production accuracy.

**Problem**: When BTC moves between addresses within the same wallet (cluster), UTXO-level tracking assigns current price as new cost basis. Wallet-level tracking preserves original acquisition price.

**Independent Test**: Can be fully tested by:
1. Creating cluster with known acquisition history
2. Moving BTC within cluster (internal transfer)
3. Verifying cost basis preserved (not updated to current price)
4. Comparing wallet_realized_cap vs utxo_realized_cap

**Acceptance Scenarios**:

1. **Given** wallet acquires 1 BTC at $50,000
   **When** BTC moves to new address in same cluster
   **Then** cost_basis remains $50,000 (not current price)

2. **Given** wallet with mixed acquisition prices ($30k, $50k, $70k)
   **When** wallet_realized_cap calculated
   **Then** matches weighted average of acquisition prices

3. **Given** wallet-level Realized Cap implemented
   **When** NUPL calculated independently (no CheckOnChain)
   **Then** deviation ≤1% from CheckOnChain reference

4. **Given** wallet-level SOPR calculated
   **When** compared to CheckOnChain
   **Then** deviation ≤2% from reference

**Current Workaround**: NUPL/SOPR endpoints use CheckOnChain values directly (NOT independent calculation). This MUST be replaced with independent wallet-level calculation.

---

## Out of Scope

- Exchange labeling (known address databases)
- Wallet fingerprinting (script type analysis)
- Temporal clustering (time-based heuristics)
- Social graph analysis
- Real-time cluster updates (batch only)

---

## References

1. **Meiklejohn, S., et al. (2013)**. "A Fistful of Bitcoins: Characterizing Payments Among Men with No Names." *ACM CCS*.
   - Foundational paper on Bitcoin address clustering
   - Multi-input heuristic formalization

2. **Ron, D., & Shamir, A. (2013)**. "Quantitative Analysis of the Full Bitcoin Transaction Graph." *Financial Cryptography*.
   - Large-scale clustering analysis
   - Change detection heuristics

3. **Möser, M., & Narayanan, A. (2017)**. "Obfuscation in Bitcoin: Techniques and Politics." *arXiv*.
   - CoinJoin protocol analysis
   - Detection challenges

4. **Wasabi Wallet Documentation**: https://docs.wasabiwallet.io/
5. **JoinMarket Documentation**: https://github.com/JoinMarket-Org/joinmarket-clientserver
6. **Whirlpool Documentation**: https://samouraiwallet.com/whirlpool
