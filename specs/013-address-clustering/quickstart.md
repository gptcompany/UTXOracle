# Quickstart: Address Clustering & CoinJoin Detection

**Feature**: spec-013 | **Date**: 2025-12-04

## Basic Usage

### Address Clustering

```python
from scripts.clustering import UnionFind, cluster_addresses

# Initialize Union-Find
uf = UnionFind()

# Process transaction inputs
tx_inputs = ["addr1", "addr2", "addr3"]
cluster_addresses(uf, tx_inputs)

# Check if addresses are in same cluster
print(uf.connected("addr1", "addr2"))  # True

# Get all clusters
clusters = uf.get_clusters()
print(f"Found {len(clusters)} clusters")
```

### CoinJoin Detection

```python
from scripts.clustering import detect_coinjoin

tx = {
    "txid": "abc123...",
    "vin": [...],   # 10 inputs
    "vout": [...]   # 10 equal outputs of 0.1 BTC
}

result = detect_coinjoin(tx)
print(f"Is CoinJoin: {result.is_coinjoin}")
print(f"Confidence: {result.confidence:.0%}")
print(f"Type: {result.coinjoin_type}")
```

### Integration with Whale Detection

```python
from scripts.whale_flow_detector import detect_whale_flow
from scripts.clustering import UnionFind, filter_coinjoins

# Filter CoinJoins before whale detection
clean_txs = filter_coinjoins(transactions)

# Cluster addresses for entity-level analysis
uf = UnionFind()
for tx in clean_txs:
    cluster_addresses(uf, tx["inputs"])

# Detect whale flows with clustering
whale_result = detect_whale_flow(
    transactions=clean_txs,
    clustering=uf,
    use_clustering=True
)
```

## Interpretation

### Cluster Size
| Size | Interpretation |
|------|----------------|
| 1 | Single-use address |
| 2-10 | Normal user |
| 10-100 | Active trader |
| 100-1000 | Service/exchange |
| >1000 | Major exchange |

### CoinJoin Confidence
| Confidence | Action |
|------------|--------|
| >0.9 | Definitely CoinJoin, exclude |
| 0.7-0.9 | Likely CoinJoin, flag |
| <0.7 | Unlikely, include |
