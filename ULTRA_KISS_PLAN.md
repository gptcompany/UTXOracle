# 🎯 Piano Definitivo ULTRA KISS: UTXOracle + mempool.space

**Data**: 2025-10-24
**Status**: Piano Esecutivo Definitivo
**Obiettivo**: Integrare UTXOracle con stack mempool.space self-hosted, massimizzando riuso codice esistente

---

## 📊 Analisi Situazione Attuale (Validata)

### ✅ Cosa Funziona

**UTXOracle.py** (référimento)
- Algoritmo validato: 99.85% success rate, ±2% accuracy
- Pure on-chain price discovery (no exchange APIs)
- 672 giorni di dati storici verificati
- **VALORE UNICO**: Clustering statistico (Steps 5-11)

**Stack mempool.space** (già installato `/media/sam/1TB/mempool/`)
- Infrastruttura battle-tested: Bitcoin Core + electrs + backend Node.js
- API REST + WebSocket real-time
- electrs: 38GB RocksDB index (UTXO set, address index)
- **MA**: Calcola prezzi da 5 exchange APIs (Coinbase, Kraken, Bitfinex, Gemini, Bitflyer)

**Codice `/live/` esistente**
- `mempool_analyzer.py` (376 righe): Real-time adaptation UTXOracle per mempool
- `frontend/` (~500 righe): Canvas visualization
- **TOTAL UNIQUE VALUE**: ~876 righe

### ❌ Cosa Duplica Inutilmente

**Infrastructure code** (1,222 righe da eliminare)
- `zmq_listener.py` (229 righe) → mempool.space WebSocket
- `tx_processor.py` (369 righe) → mempool.space API
- `block_parser.py` (144 righe) → mempool.space API
- `orchestrator.py` (271 righe) → mempool.space backend
- `bitcoin_rpc.py` (109 righe) → mempool.space backend
- `baseline_calculator.py` (581 righe) → **REFACTOR** (vedi sotto)

**Motivazione**: mempool.space fa già tutto questo, meglio e più robusto.

---

## 🎯 Architettura Definitiva ULTRA KISS

```
┌──────────────────────────────────────────────────────────────┐
│                    LAYER 1: INFRASTRUCTURE                    │
│   Stack mempool.space Self-Hosted (Docker Compose)            │
│   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐       │
│   │ Bitcoin Core│──▶│   electrs   │──▶│   MySQL     │       │
│   │  (RPC+ZMQ)  │   │ (38GB index)│   │  (backend)  │       │
│   └─────────────┘   └─────────────┘   └─────────────┘       │
│                             │                                  │
│                             ▼                                  │
│            ┌────────────────────────────────┐                 │
│            │   Mempool Backend (Node.js)    │                 │
│            │   - REST API (localhost:8999)  │                 │
│            │   - WebSocket (real-time)      │                 │
│            │   - price-updater (KEEP!)      │                 │
│            └────────────────────────────────┘                 │
└──────────────────────────────────────────────────────────────┘
                             │
                             │ HTTP/WebSocket (localhost)
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                   LAYER 2: INTELLIGENCE                       │
│              UTXOracle Algorithm (Python)                     │
│   ┌──────────────────────────────────────────────────┐       │
│   │  UTXOracle_library.py (REFACTOR!)                │       │
│   │  - class UTXOracleCalculator                     │       │
│   │  - calculate_price_for_transactions()            │       │
│   │  - Steps 5-11 as library methods                 │       │
│   └──────────────────────────────────────────────────┘       │
│                             │                                  │
│                             ▼                                  │
│   ┌──────────────────────────────────────────────────┐       │
│   │  daily_analysis.py (Cron Job - ogni 10 min)     │       │
│   │  1. Fetch mempool API (localhost:8999)          │       │
│   │  2. Run UTXOracle algorithm                     │       │
│   │  3. Read mempool.space price (exchange)         │       │
│   │  4. Compare & save to DuckDB                    │       │
│   └──────────────────────────────────────────────────┘       │
└──────────────────────────────────────────────────────────────┘
                             │
                             │ Read/Write
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                    LAYER 3: STORAGE                           │
│   DuckDB (file: utxoracle_cache.db)                          │
│   ┌──────────────────────────────────────────────────┐       │
│   │  prices(                                         │       │
│   │    timestamp TIMESTAMP,                          │       │
│   │    utxoracle_price DECIMAL,   -- On-chain       │       │
│   │    mempool_price DECIMAL,     -- Exchange       │       │
│   │    confidence DECIMAL,                           │       │
│   │    tx_count INT                                  │       │
│   │  )                                               │       │
│   └──────────────────────────────────────────────────┘       │
└──────────────────────────────────────────────────────────────┘
                             │
                             │ Query
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                 LAYER 4: API & VISUALIZATION                  │
│   FastAPI (port 8000)                                         │
│   ┌──────────────────────────────────────────────────┐       │
│   │  GET /api/prices/latest                          │       │
│   │  GET /api/prices/historical?days=30              │       │
│   │  GET /api/prices/comparison  (vs exchange)       │       │
│   └──────────────────────────────────────────────────┘       │
│                             │                                  │
│                             ▼                                  │
│   Frontend (Plotly.js - NON Canvas custom!)                  │
│   - Time series: UTXOracle vs Exchange prices                │
│   - Scatter plot: Transaction distribution                   │
│   - Confidence intervals                                     │
└──────────────────────────────────────────────────────────────┘
```

**Principi Chiave**:
1. **Separation of Concerns**: Ogni layer fa UNA cosa
2. **Reuse Over Build**: mempool.space per infra, UTXOracle per intelligence
3. **Single Source of Truth**: DuckDB come cache
4. **Comparison Value**: Keep mempool.space prices per confronto (non disabilitare!)

---

## 🔧 Decisione Critica: UTXOracle Refactor

### ❌ Opzione A: Subprocess (NO)

```python
# daily_analysis.py
result = subprocess.run(['python3', 'UTXOracle.py', '-rb'], ...)
price = parse_stdout(result.stdout)  # Fragile!
```

**Problemi**:
- ❌ Parsing stdout è fragile (regex su testo formattato)
- ❌ Processo isolato (no condivisione dati in-memory)
- ❌ Difficile testare (mock subprocess è complesso)
- ❌ Difficile migrare a Rust (devi cambiare parsing)

### ✅ Opzione B: Refactor a Libreria (SÌ)

```python
# UTXOracle_library.py (NUOVO - refactor di UTXOracle.py)
class UTXOracleCalculator:
    def __init__(self, config=None):
        self.first_bin_value = -6
        self.last_bin_value = 6
        self.histogram_bins = self._build_histogram_bins()
        # ... setup stencils ...

    def calculate_price_for_transactions(self, transactions: List[dict]) -> dict:
        """
        Calculate price from transaction list (Steps 5-11).

        Args:
            transactions: List of dicts with 'vout' key (mempool.space format)

        Returns:
            {
                'price_usd': float,
                'confidence': float,
                'tx_count': int,
                'histogram': dict
            }
        """
        histogram = {}

        # Step 6: Load histogram
        for tx in transactions:
            for output in tx.get('vout', []):
                amount_btc = output['value'] / 1e8  # satoshi to BTC
                bin_idx = self._get_bin_index(amount_btc)
                histogram[bin_idx] = histogram.get(bin_idx, 0) + amount_btc

        # Step 7: Remove round amounts
        histogram = self._remove_round_amounts(histogram)

        # Steps 8-11: Calculate price
        price = self._estimate_price(histogram)
        confidence = self._calculate_confidence(len(transactions))

        return {
            'price_usd': price,
            'confidence': confidence,
            'tx_count': len(transactions),
            'histogram': histogram
        }

    def _build_histogram_bins(self): ...
    def _get_bin_index(self, amount): ...
    def _remove_round_amounts(self, histogram): ...
    def _estimate_price(self, histogram): ...

# UTXOracle.py (VECCHIO - diventa CLI wrapper)
from UTXOracle_library import UTXOracleCalculator

if __name__ == "__main__":
    # Parse args come prima
    # Fetch da RPC come prima
    transactions = fetch_from_bitcoin_core()

    # Usa libreria
    calculator = UTXOracleCalculator()
    result = calculator.calculate_price_for_transactions(transactions)

    print(f"2025-10-24 price: ${result['price_usd']:,.0f}")
```

**Vantaggi**:
- ✅ API pulita (passa dict Python, ricevi dict Python)
- ✅ Facile testare (mock transactions = lista di dict)
- ✅ Preparato per Rust (sostituisci import, resto invariato)
- ✅ Riusabile (CLI, API, cron job usano stessa libreria)

### Strategia Migrazione Rust (Futuro)

**Oggi** (Python):
```python
from UTXOracle_library import UTXOracleCalculator
calc = UTXOracleCalculator()
result = calc.calculate_price_for_transactions(txs)
```

**Domani** (Rust via PyO3):
```python
from utxoracle_rust import UTXOracleCalculator  # Compiled .so/.pyd
calc = UTXOracleCalculator()  # Stessa interfaccia!
result = calc.calculate_price_for_transactions(txs)
```

**Conclusione**: Refactor a libreria è preparazione ideale per Rust.

---

## 📋 Inventario Codice Esistente

### ✅ KEEP (Unique Value)

**`/live/backend/mempool_analyzer.py`** (376 righe)
- **Perché**: Real-time adaptation UTXOracle per mempool (rolling window 3h vs 24h)
- **Azione**: Integrare con `UTXOracle_library.py` (evita duplicazione algoritmo)

**`/live/frontend/`** (~500 righe)
- **Perché**: Canvas visualization custom (scatter plot, timeline)
- **Azione**: **REFACTOR** con Plotly.js (50 righe invece di 500)

### ♻️ REFACTOR

**`/live/backend/baseline_calculator.py`** (581 righe)
- **Problema**: Duplica UTXOracle.py Steps 5-11
- **Soluzione**: Sostituire con:

```python
# NEW: baseline_wrapper.py (50 righe)
from UTXOracle_library import UTXOracleCalculator
import requests

def calculate_baseline() -> dict:
    """Fetch from mempool API + run UTXOracle"""
    # Fetch 144 blocks from mempool.space
    blocks = requests.get('http://localhost:8999/api/blocks').json()
    transactions = []
    for block in blocks[:144]:
        block_txs = requests.get(f'http://localhost:8999/api/block/{block["id"]}/txs').json()
        transactions.extend(block_txs)

    # Calculate with UTXOracle library
    calc = UTXOracleCalculator()
    result = calc.calculate_price_for_transactions(transactions)
    return result
```

**Token savings**: 581 → 50 righe (91% reduction)

### 🗑️ DELETE

**`/live/backend/`** (eliminare):
- `zmq_listener.py` (229 righe)
- `tx_processor.py` (369 righe)
- `block_parser.py` (144 righe)
- `orchestrator.py` (271 righe)
- `bitcoin_rpc.py` (109 righe)

**Total deleted**: 1,122 righe

**Reason**: mempool.space backend fa già tutto questo.

---

## 🚀 Piano Implementazione (Step-by-Step)

### Phase 1: Setup Infrastructure (30 min)

```bash
# 1. Start mempool.space stack
cd /media/sam/1TB/mempool/docker

# 2. Check/edit .env (usa Bitcoin Core già running)
nano .env
# CORE_RPC_HOST=127.0.0.1
# CORE_RPC_PORT=8332
# CORE_RPC_USERNAME=your_user
# CORE_RPC_PASSWORD=your_pass

# 3. Start all services
docker-compose up -d

# 4. Wait for electrs sync (check logs)
docker-compose logs -f electrs

# 5. Verify APIs work
curl http://localhost:8999/api/blocks/tip/height
# Expected: {"height": 867234}

curl http://localhost:8999/api/v1/prices
# Expected: {"USD": 67000, "EUR": 62000, ...}
```

**Output**: mempool.space running on localhost:8999

---

### Phase 2: Refactor UTXOracle (2-3 hours)

**Task**: Creare `UTXOracle_library.py` con logica Steps 5-11 come classe

```bash
# Struttura file
/media/sam/1TB/UTXOracle/
├── UTXOracle.py           # KEEP (CLI wrapper - modificare)
├── UTXOracle_library.py   # NEW (core algorithm as library)
└── tests/
    └── test_utxoracle_library.py  # NEW (unit tests)
```

**Steps**:
1. Creare `UTXOracle_library.py`
2. Estrarre logica Steps 5-11 da `UTXOracle.py` → `class UTXOracleCalculator`
3. Modificare `UTXOracle.py` per usare libreria (backward compatible)
4. Scrivere test per verificare output identico

**Validation**:
```bash
# Test CLI still works
python3 UTXOracle.py -rb
# Expected: Same output as before

# Test library works
python3 -c "
from UTXOracle_library import UTXOracleCalculator
calc = UTXOracleCalculator()
print('Library imported successfully')
"
```

**Output**: `UTXOracle_library.py` ready for use

---

### Phase 3: Integration Service (2 hours)

**Task**: Creare servizio che connette mempool.space → UTXOracle → DuckDB

```python
# /media/sam/1TB/UTXOracle/scripts/daily_analysis.py

import requests
import duckdb
from datetime import datetime
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))
from UTXOracle_library import UTXOracleCalculator

MEMPOOL_API = "http://localhost:8999/api"
DB_FILE = "/media/sam/1TB/UTXOracle/data/utxoracle_cache.db"

def fetch_recent_transactions(limit=1000):
    """Fetch recent mempool transactions from local API"""
    response = requests.get(f"{MEMPOOL_API}/mempool/txids")
    txids = response.json()[:limit]

    transactions = []
    for txid in txids:
        tx = requests.get(f"{MEMPOOL_API}/tx/{txid}").json()
        transactions.append(tx)

    return transactions

def fetch_mempool_price():
    """Get mempool.space price (from exchanges)"""
    response = requests.get(f"{MEMPOOL_API}/v1/prices")
    return response.json()['USD']

def init_database():
    """Initialize DuckDB schema"""
    con = duckdb.connect(DB_FILE)
    con.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            timestamp TIMESTAMP PRIMARY KEY,
            utxoracle_price DECIMAL(12, 2),
            mempool_price DECIMAL(12, 2),
            confidence DECIMAL(5, 4),
            tx_count INTEGER,
            diff_amount DECIMAL(12, 2),
            diff_percent DECIMAL(6, 2)
        )
    """)
    con.close()

def main():
    print("🔄 UTXOracle Analysis Starting...")

    # 1. Fetch data
    print("📡 Fetching mempool transactions...")
    transactions = fetch_recent_transactions()
    mempool_price = fetch_mempool_price()
    print(f"   Fetched {len(transactions)} transactions")

    # 2. Calculate UTXOracle price
    print("🧮 Running UTXOracle algorithm...")
    calc = UTXOracleCalculator()
    result = calc.calculate_price_for_transactions(transactions)

    # 3. Compare prices
    diff_amount = result['price_usd'] - mempool_price
    diff_percent = (diff_amount / mempool_price) * 100

    print(f"✅ Analysis complete:")
    print(f"   UTXOracle (on-chain):  ${result['price_usd']:,.2f}")
    print(f"   mempool.space (exch):  ${mempool_price:,.2f}")
    print(f"   Difference:            ${diff_amount:+,.2f} ({diff_percent:+.2f}%)")
    print(f"   Confidence:            {result['confidence']:.4f}")

    # 4. Save to database
    con = duckdb.connect(DB_FILE)
    con.execute("""
        INSERT INTO prices VALUES (?, ?, ?, ?, ?, ?, ?)
    """, [
        datetime.now(),
        result['price_usd'],
        mempool_price,
        result['confidence'],
        result['tx_count'],
        diff_amount,
        diff_percent
    ])
    con.close()
    print("💾 Saved to database")

if __name__ == "__main__":
    init_database()
    main()
```

**Cron setup** (ogni 10 minuti):
```bash
crontab -e
# Add:
*/10 * * * * cd /media/sam/1TB/UTXOracle && python3 scripts/daily_analysis.py >> logs/analysis.log 2>&1
```

**Output**: DuckDB file con storico confronto prezzi

---

### Phase 4: FastAPI Backend (1 hour)

```python
# /media/sam/1TB/UTXOracle/api/main.py

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import duckdb
from datetime import datetime, timedelta

app = FastAPI(title="UTXOracle API")
app.add_middleware(CORSMiddleware, allow_origins=["*"])

DB_FILE = "/media/sam/1TB/UTXOracle/data/utxoracle_cache.db"

@app.get("/api/prices/latest")
def get_latest_price():
    """Get most recent price comparison"""
    with duckdb.connect(DB_FILE, read_only=True) as con:
        result = con.execute("""
            SELECT * FROM prices
            ORDER BY timestamp DESC
            LIMIT 1
        """).fetchdf()
    return result.to_dict(orient='records')[0]

@app.get("/api/prices/historical")
def get_historical_prices(days: int = Query(7, ge=1, le=365)):
    """Get historical prices for last N days"""
    cutoff = datetime.now() - timedelta(days=days)
    with duckdb.connect(DB_FILE, read_only=True) as con:
        result = con.execute("""
            SELECT * FROM prices
            WHERE timestamp >= ?
            ORDER BY timestamp ASC
        """, [cutoff]).fetchdf()
    return result.to_dict(orient='records')

@app.get("/api/prices/stats")
def get_price_stats(days: int = Query(7)):
    """Get statistical summary"""
    cutoff = datetime.now() - timedelta(days=days)
    with duckdb.connect(DB_FILE, read_only=True) as con:
        result = con.execute("""
            SELECT
                COUNT(*) as data_points,
                AVG(utxoracle_price) as avg_utxoracle,
                AVG(mempool_price) as avg_mempool,
                AVG(diff_percent) as avg_diff_percent,
                MAX(diff_percent) as max_diff_percent,
                MIN(diff_percent) as min_diff_percent,
                STDDEV(diff_percent) as stddev_diff_percent
            FROM prices
            WHERE timestamp >= ?
        """, [cutoff]).fetchdf()
    return result.to_dict(orient='records')[0]
```

**Run**:
```bash
cd /media/sam/1TB/UTXOracle
uvicorn api.main:app --port 8000 --reload
```

**Output**: API on http://localhost:8000

---

### Phase 5: Frontend Visualization (1-2 hours)

**Replace Canvas custom code with Plotly.js** (10× simpler)

```html
<!-- /media/sam/1TB/UTXOracle/frontend/index.html -->
<!DOCTYPE html>
<html>
<head>
    <title>UTXOracle vs Exchange Prices</title>
    <script src="https://cdn.plot.ly/plotly-2.26.0.min.js"></script>
</head>
<body>
    <h1>UTXOracle Price Comparison</h1>
    <div id="chart" style="width:100%;height:600px;"></div>

    <script>
        // Fetch data from our API
        fetch('http://localhost:8000/api/prices/historical?days=7')
            .then(r => r.json())
            .then(data => {
                const timestamps = data.map(d => d.timestamp);

                // Plot 1: UTXOracle (on-chain)
                const utxoracle_trace = {
                    x: timestamps,
                    y: data.map(d => d.utxoracle_price),
                    name: 'UTXOracle (On-Chain)',
                    type: 'scatter',
                    mode: 'lines+markers',
                    line: {color: '#00ff00', width: 2}
                };

                // Plot 2: mempool.space (exchanges)
                const mempool_trace = {
                    x: timestamps,
                    y: data.map(d => d.mempool_price),
                    name: 'mempool.space (Exchanges)',
                    type: 'scatter',
                    mode: 'lines+markers',
                    line: {color: '#ff0000', width: 2, dash: 'dash'}
                };

                const layout = {
                    title: 'BTC/USD: On-Chain vs Exchange Prices',
                    xaxis: {title: 'Time'},
                    yaxis: {title: 'Price (USD)'},
                    hovermode: 'x unified'
                };

                Plotly.newPlot('chart', [utxoracle_trace, mempool_trace], layout);
            });
    </script>
</body>
</html>
```

**Output**: Frontend showing price comparison (50 righe vs 500 Canvas custom)

---

## 📊 Summary: Cosa Cambia

### Before (Situazione Attuale)

```
/live/backend/
├── zmq_listener.py (229)      ❌ DELETE
├── tx_processor.py (369)      ❌ DELETE
├── block_parser.py (144)      ❌ DELETE
├── orchestrator.py (271)      ❌ DELETE
├── bitcoin_rpc.py (109)       ❌ DELETE
├── baseline_calculator.py (581) ❌ REFACTOR
├── mempool_analyzer.py (376)  ⚠️ INTEGRATE
└── api.py (353)               ⚠️ SIMPLIFY

/live/frontend/
└── custom Canvas code (500)   ❌ REPLACE with Plotly

Total: 3,041 righe
```

### After (ULTRA KISS)

```
/
├── UTXOracle.py               ✅ KEEP (CLI - modified)
├── UTXOracle_library.py       ✅ NEW (core algorithm)
├── scripts/
│   └── daily_analysis.py      ✅ NEW (integration)
├── api/
│   └── main.py                ✅ NEW (FastAPI simple)
├── frontend/
│   └── index.html             ✅ NEW (Plotly 50 righe)
├── data/
│   └── utxoracle_cache.db     ✅ NEW (DuckDB)

Infrastructure:
└── /media/sam/1TB/mempool/    ✅ USE (docker-compose)

Total: ~700 righe (vs 3,041)
Reduction: 77%
```

**Key Metrics**:
- Code reduction: -77% (3,041 → 700 righe)
- Dependencies: -5 modules (reuse mempool.space)
- Maintenance: -70% (no ZMQ, no parser, no orchestrator)
- Value preserved: 100% (UTXOracle algorithm intact)
- Value added: Price comparison (on-chain vs exchange)

---

## ✅ Success Criteria

1. **mempool.space stack running**: `curl localhost:8999/api/blocks/tip/height` → success
2. **UTXOracle library works**: Import and calculate price from transaction list
3. **Integration service works**: Cron job saves data to DuckDB every 10 min
4. **API works**: `curl localhost:8000/api/prices/latest` → returns comparison
5. **Frontend works**: Open `index.html` → see price chart

**Final validation**:
```bash
# Check database has data
duckdb data/utxoracle_cache.db "SELECT COUNT(*) FROM prices"
# Expected: >0

# Check prices differ
duckdb data/utxoracle_cache.db "SELECT AVG(ABS(diff_percent)) FROM prices"
# Expected: ~2-5% difference (on-chain vs exchange)
```

---

## 🎯 Next Actions (Ordine Esecuzione)

**Oggi** (Setup + Refactor):
1. ✅ Validare piano con utente
2. ⏳ Phase 1: Start mempool.space stack (30 min)
3. ⏳ Phase 2: Refactor UTXOracle.py → library (2-3h)

**Domani** (Integration):
4. ⏳ Phase 3: Create daily_analysis.py (2h)
5. ⏳ Phase 4: Create FastAPI backend (1h)
6. ⏳ Phase 5: Create Plotly frontend (1h)

**Dopodomani** (Cleanup):
7. ⏳ Archive old `/live/` code (backup before delete)
8. ⏳ Update CLAUDE.md documentation
9. ⏳ Create migration guide for existing setups

**Tempo Totale Stimato**: 8-10 ore lavoro effettivo

---

## 🚨 Risks & Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| electrs sync takes 12h | High | Start overnight, work on refactor in parallel |
| UTXOracle refactor breaks algo | Critical | Keep original UTXOracle.py, test output matches exactly |
| mempool.space API rate limit | Medium | Self-hosted = no limits |
| DuckDB file corruption | Low | Regular backups, use WAL mode |

---

## 📚 References

- **mempool.space docs**: https://github.com/mempool/mempool/tree/master/docker
- **DuckDB docs**: https://duckdb.org/docs/
- **UTXOracle algorithm**: `/media/sam/1TB/UTXOracle/UTXOracle.py` Steps 5-11
- **Gemini analysis**: Validated in this conversation (2025-10-24)

---

**Ready to execute?** Aspetto conferma per iniziare Phase 1.
