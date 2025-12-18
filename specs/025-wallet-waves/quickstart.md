# Quickstart: Wallet Waves & Absorption Rates

**Spec**: spec-025
**Prerequisites**: DuckDB with `utxo_lifecycle_full` VIEW populated

## 1. Verify Data Availability

```bash
# Check VIEW exists and has address column
cd /media/sam/1TB/UTXOracle
python -c "
import duckdb
conn = duckdb.connect('data/utxoracle.db', read_only=True)
result = conn.execute('SELECT COUNT(*), COUNT(DISTINCT address) FROM utxo_lifecycle_full WHERE is_spent = FALSE').fetchone()
print(f'Unspent UTXOs: {result[0]:,}')
print(f'Unique addresses: {result[1]:,}')
"
```

Expected output:
```
Unspent UTXOs: ~150,000,000
Unique addresses: ~50,000,000
```

## 2. Test Wallet Waves Calculation

```bash
# Run wallet waves calculation
python -c "
from scripts.metrics.wallet_waves import calculate_wallet_waves
import duckdb

conn = duckdb.connect('data/utxoracle.db', read_only=True)
result = calculate_wallet_waves(conn, block_height=876543)

print('=== Wallet Waves ===')
for band in result.bands:
    print(f'{band.band.value:10} | {band.supply_btc:>12,.2f} BTC | {band.supply_pct:>6.2f}% | {band.address_count:>10,} addresses')

print(f'\\nRetail: {result.retail_supply_pct:.2f}%')
print(f'Institutional: {result.institutional_supply_pct:.2f}%')
"
```

Expected output:
```
=== Wallet Waves ===
shrimp     |  1,234,567.89 BTC |   6.27% | 45,000,000 addresses
crab       |  2,345,678.90 BTC |  11.91% |  2,500,000 addresses
fish       |  3,456,789.01 BTC |  17.55% |    250,000 addresses
shark      |  4,567,890.12 BTC |  23.19% |     25,000 addresses
whale      |  5,678,901.23 BTC |  28.83% |      2,500 addresses
humpback   |  2,415,172.85 BTC |  12.25% |        150 addresses

Retail: 35.73%
Institutional: 64.27%
```

## 3. Test API Endpoint

```bash
# Start API server (if not running)
cd /media/sam/1TB/UTXOracle
uv run uvicorn api.main:app --reload --port 8000 &

# Test wallet waves endpoint
curl -s http://localhost:8000/api/metrics/wallet-waves | python -m json.tool

# Test absorption rates endpoint
curl -s "http://localhost:8000/api/metrics/absorption-rates?window=30d" | python -m json.tool
```

Expected response (wallet-waves):
```json
{
    "timestamp": "2025-12-17T12:00:00Z",
    "block_height": 876543,
    "total_supply_btc": 19700000.0,
    "bands": [
        {"band": "shrimp", "supply_btc": 1234567.89, "supply_pct": 6.27, "address_count": 45000000, "avg_balance": 0.027},
        ...
    ],
    "retail_supply_pct": 35.73,
    "institutional_supply_pct": 64.27,
    "address_count_total": 50000000,
    "null_address_btc": 12345.67,
    "confidence": 0.85
}
```

## 4. Run Tests

```bash
# Run all wallet waves tests
cd /media/sam/1TB/UTXOracle
uv run pytest tests/test_wallet_waves.py tests/test_absorption_rates.py -v

# Check coverage
uv run pytest tests/test_wallet_waves.py tests/test_absorption_rates.py --cov=scripts/metrics --cov-report=term-missing
```

Expected: All tests pass, 80%+ coverage.

## 5. Performance Validation

```bash
# Measure calculation time
python -c "
import time
import duckdb
from scripts.metrics.wallet_waves import calculate_wallet_waves

conn = duckdb.connect('data/utxoracle.db', read_only=True)

start = time.perf_counter()
result = calculate_wallet_waves(conn, block_height=876543)
elapsed = time.perf_counter() - start

print(f'Wallet waves calculation: {elapsed:.2f}s')
assert elapsed < 5.0, f'Performance requirement failed: {elapsed:.2f}s > 5.0s'
print('✅ Performance requirement met (<5s)')
"
```

## Troubleshooting

### "address column not found"
The `utxo_lifecycle_full` VIEW needs to include the address column from chainstate import.

```bash
# Verify VIEW definition
python -c "
import duckdb
conn = duckdb.connect('data/utxoracle.db')
print(conn.execute('DESCRIBE utxo_lifecycle_full').fetchall())
"
```

### "No addresses found"
Ensure chainstate was imported with address decoding enabled.

```bash
# Check for addresses
python -c "
import duckdb
conn = duckdb.connect('data/utxoracle.db')
result = conn.execute('SELECT COUNT(*) FROM utxo_lifecycle_full WHERE address IS NOT NULL').fetchone()
print(f'UTXOs with addresses: {result[0]:,}')
"
```

### Performance issues (>5s)
Check if address index exists:

```bash
python -c "
import duckdb
conn = duckdb.connect('data/utxoracle.db')
conn.execute('CREATE INDEX IF NOT EXISTS idx_utxo_address ON utxo_lifecycle(address)')
print('Index created/verified')
"
```
