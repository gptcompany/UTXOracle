# Address Clustering Performance Guide

## Current Performance Benchmarks (December 2025)

### Hardware
- CPU: Multi-core (tested with 16 workers)
- RAM: 110GB available
- Storage: NVMe SSD (6.2 GB/s read)
- Bitcoin Core: v30.0.0

### Method Comparison

| Method | Speed | RAM Usage | Time for Full Blockchain |
|--------|-------|-----------|--------------------------|
| RPC v3 single-threaded | ~0.7 blocks/sec | Low | ~15 days |
| Batch RPC (100 hashes) | ~17 blocks/sec | Low | ~14 hours |
| Batch RPC + 16 workers | ~1000 blocks/min | Medium | ~15 hours |
| Pair extraction → UnionFind | ~0.3M pairs/sec | High | ~3-4 hours (Phase 2) |

### Recommended Approach: Two-Phase Pipeline

**Phase 1: Extract pairs** (run_clustering_optimized.py)
- Uses batch RPC + multiprocessing
- Outputs compressed CSV files
- ~15 hours for full blockchain

**Phase 2: UnionFind clustering** (complete_clustering_v2.py)
- Memory-optimized with numpy arrays
- Processes pre-extracted pairs
- ~3-4 hours for 2B pairs
- Checkpoints after each file

### Scripts

1. **run_clustering_optimized.py** - Full pipeline (Phase 1 + Phase 2)
   ```bash
   nohup uv run python -m scripts.bootstrap.run_clustering_optimized \
       --workers 16 --batch-size 100 > /tmp/clustering.log 2>&1 &
   ```

2. **complete_clustering_v2.py** - Phase 2 only (when pairs already extracted)
   ```bash
   nohup uv run python -m scripts.bootstrap.complete_clustering_v2 \
       > /tmp/clustering_v2.log 2>&1 &
   ```

### Memory Optimization

The v2 script uses:
- **Integer IDs** instead of string addresses (5x less RAM)
- **Numpy arrays** for UnionFind parent/rank
- **Disk checkpoints** after each file

Memory formula: `num_addresses × 5 bytes` (vs ~100 bytes with strings)

Example: 500M addresses = 2.5GB (vs 50GB with strings)

### Known Issues

1. **bitcoin-iterate incompatibility**: Bitcoin Core v30+ uses a different block file format. The `bitcoin-iterate` C tool cannot parse these files.

2. **RPC rate limiting**: Bitcoin Core may throttle RPC requests. Use batch calls to reduce overhead.

3. **Python GIL**: Use `multiprocessing` (not `threading`) for true parallelism.

### Future Optimizations

1. **Cython**: Compile UnionFind to C for 3-5x speedup
2. **PyPy**: JIT compilation for 5-10x speedup on pure Python
3. **Rust rewrite**: For maximum performance (10-50x potential)

### Monitoring

```bash
# Check progress
tail -f /tmp/clustering_v2.log

# Check memory usage
ps aux | grep complete_clustering | awk '{print $6/1024/1024 " GB"}'

# Check process health
ps -p $(pgrep -f complete_clustering) -o etime,pcpu,pmem,rss
```
