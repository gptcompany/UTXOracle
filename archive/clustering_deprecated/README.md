# Deprecated Clustering Scripts

Archived on 2025-12-23. These scripts were superseded by V3 ultra-fast clustering.

## Why Deprecated

| Script | Issue |
|--------|-------|
| `complete_clustering.py` | V1: Pure Python, too slow (~8h for 2B pairs) |
| `complete_clustering_v2.py` | V2: Numpy-based, crashed on large files, no checkpoints |
| `run_address_clustering.py` | Helper script for V1 |
| `run_clustering_only.py` | Helper script for V1/V2 |
| `run_clustering_optimized.py` | Attempted optimization, still too slow |

## Current Approach

Use `scripts/bootstrap/complete_clustering_v3_fast.py` which features:
- Cython-compiled UnionFind (60-100x faster)
- PyArrow streaming for large files
- Checkpoint after each file (resume capability)
- Target: 60-90 min for 2B pairs (vs 3-8h)

## Usage

```bash
# Compile Cython first
cd scripts/bootstrap/cython_uf
python setup.py build_ext --inplace

# Run clustering
python -m scripts.bootstrap.complete_clustering_v3_fast
```
