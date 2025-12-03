# Quickstart: On-Chain Metrics Core

**Feature**: 007-onchain-metrics-core
**Time to implement**: ~1-2 days
**LOC estimate**: ~330

## Prerequisites

Before starting implementation:

1. **Branch**: Ensure you're on `007-onchain-metrics-core`
   ```bash
   git checkout 007-onchain-metrics-core
   ```

2. **Dependencies**: No new dependencies required (pure Python)
   ```bash
   # Verify existing setup
   uv run python -c "import duckdb, pydantic; print('OK')"
   ```

3. **Services**: Ensure infrastructure is running
   ```bash
   # Bitcoin Core
   bitcoin-cli getblockcount

   # DuckDB (existing)
   ls -la /media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db
   ```

## Implementation Order (KISS)

### Step 1: TX Volume USD (~80 LOC, ~2h)

**Why first**: Simplest, leverages existing tx data, validates integration pattern.

```bash
# 1. Create test first (TDD RED)
touch tests/test_onchain_metrics.py

# 2. Implement module
touch scripts/metrics/__init__.py
touch scripts/metrics/tx_volume.py

# 3. Run tests (TDD GREEN)
uv run pytest tests/test_onchain_metrics.py::test_tx_volume -v
```

**Key functions to implement**:
```python
# scripts/metrics/tx_volume.py
def calculate_tx_volume(transactions: list[dict], utxoracle_price: float, confidence: float) -> TxVolumeMetric:
    """Calculate total BTC and USD transaction volume."""
    pass

def estimate_real_volume(tx: dict) -> float:
    """Estimate transfer volume excluding change outputs."""
    pass
```

### Step 2: Active Addresses (~100 LOC, ~2h)

**Why second**: Builds on tx iteration pattern from Step 1.

```bash
# 1. Add tests (TDD RED)
# Add to tests/test_onchain_metrics.py

# 2. Implement module
touch scripts/metrics/active_addresses.py

# 3. Run tests (TDD GREEN)
uv run pytest tests/test_onchain_metrics.py::test_active_addresses -v
```

**Key functions to implement**:
```python
# scripts/metrics/active_addresses.py
def count_active_addresses(transactions: list[dict]) -> ActiveAddressesMetric:
    """Count unique addresses from inputs and outputs."""
    pass

def detect_anomaly(current_count: int, historical_counts: list[int]) -> bool:
    """Detect if current count is >3σ from moving average."""
    pass
```

### Step 3: Monte Carlo Fusion (~150 LOC, ~3h)

**Why third**: Most complex, requires understanding of existing signal fusion.

```bash
# 1. Add tests (TDD RED)
# Add to tests/test_onchain_metrics.py

# 2. Implement module
touch scripts/metrics/monte_carlo_fusion.py

# 3. Run tests (TDD GREEN)
uv run pytest tests/test_onchain_metrics.py::test_monte_carlo -v
```

**Key functions to implement**:
```python
# scripts/metrics/monte_carlo_fusion.py
def monte_carlo_fusion(
    whale_vote: float, whale_confidence: float,
    utxo_vote: float, utxo_confidence: float,
    n_samples: int = 1000
) -> MonteCarloFusionResult:
    """Bootstrap sample signal fusion with confidence intervals."""
    pass

def detect_bimodal(samples: list[float]) -> str:
    """Detect if distribution is bimodal."""
    pass

def determine_action(signal_mean: float, ci_lower: float, ci_upper: float) -> tuple[str, float]:
    """Determine action and confidence from signal distribution."""
    pass
```

### Step 4: DuckDB Schema (~30 min)

```bash
# Create migration script
touch scripts/init_metrics_db.py

# Run migration
uv run python scripts/init_metrics_db.py
```

### Step 5: Integration (~100 LOC, ~2h)

```bash
# 1. Modify daily_analysis.py to call new metrics
# 2. Add to main() flow after price calculation

# 3. Integration test
uv run pytest tests/integration/test_metrics_integration.py -v
```

### Step 6: API Endpoint (~50 LOC, ~1h)

```bash
# 1. Add endpoint to api/main.py
# 2. Test endpoint
curl http://localhost:8000/api/metrics/latest | jq
```

## File Checklist

After implementation, verify these files exist:

```
✅ scripts/metrics/__init__.py
✅ scripts/metrics/tx_volume.py
✅ scripts/metrics/active_addresses.py
✅ scripts/metrics/monte_carlo_fusion.py
✅ scripts/models/metrics_models.py
✅ scripts/init_metrics_db.py
✅ tests/test_onchain_metrics.py
✅ tests/integration/test_metrics_integration.py
```

## Validation Commands

```bash
# Run all metrics tests
uv run pytest tests/test_onchain_metrics.py -v --cov=scripts/metrics

# Check coverage (target: ≥80%)
uv run pytest --cov=scripts/metrics --cov-report=term-missing

# Test API endpoint
curl http://localhost:8000/api/metrics/latest | jq

# Performance validation
uv run python -c "
from scripts.metrics.monte_carlo_fusion import monte_carlo_fusion
import time
start = time.time()
for _ in range(100):
    monte_carlo_fusion(0.8, 0.9, 0.7, 0.85)
elapsed = (time.time() - start) / 100 * 1000
print(f'Monte Carlo avg: {elapsed:.1f}ms (target: <100ms)')
"
```

## Common Issues

### Issue: Import errors
```bash
# Ensure scripts/ is in Python path
export PYTHONPATH="${PYTHONPATH}:/media/sam/1TB/UTXOracle"
```

### Issue: DuckDB locked
```bash
# Check for existing connections
lsof | grep utxoracle_cache.db

# Restart daily_analysis if needed
sudo systemctl restart utxoracle-daily
```

### Issue: Monte Carlo too slow
```python
# Use list comprehension instead of loop
samples = [
    0.7 * (whale_vote if random.random() < whale_conf else 0) +
    0.3 * (utxo_vote if random.random() < utxo_conf else 0)
    for _ in range(n_samples)
]
```

## Next Steps

After completing spec-007:

1. Run `/speckit.tasks` to generate detailed task breakdown
2. Create PR for review
3. Merge and deploy
4. Proceed to spec-008 (Derivatives Historical Integration)
