# 🔬 On-Chain Metrics Analysis: CheckOnChain Replication Plan

**Riferimento**:
- MVRV STH: https://charts.checkonchain.com/btconchain/unrealised/mvrv_sth/mvrv_sth_light.html
- URPD Heatmap: https://charts.checkonchain.com/btconchain/premium/urpd_heatmap_supply/urpd_heatmap_supply_light.html

---

## 📊 Cosa Sono Queste Metriche?

### 1. MVRV (Market Value to Realized Value) - Short-Term Holders

**Formula**:
```
MVRV = Market Cap / Realized Cap

Dove:
- Market Cap = Current Price × Total Supply
- Realized Cap = Σ(UTXO_value × Price_when_created)
```

**Interpretazione**:
- **MVRV > 1**: Mercato in profitto (prezzo attuale > prezzo medio acquisizione)
- **MVRV < 1**: Mercato in perdita (prezzo attuale < prezzo medio acquisizione)
- **MVRV STH (Short-Term Holders)**: Solo UTXO creati negli ultimi 155 giorni

**Caso d'uso**: Identificare top/bottom di mercato
- MVRV STH > 2.0 → Top locale probabile (retail FOMO)
- MVRV STH < 0.8 → Bottom locale probabile (capitulazione)

---

### 2. URPD (UTXO Realized Price Distribution) Heatmap

**Definizione**:
Distribuzione degli UTXO per **prezzo di acquisizione** (realized price) nel tempo.

**Visualizzazione**:
- **Asse X**: Tempo (date)
- **Asse Y**: Prezzo BTC/USD
- **Colore**: Quantità di BTC agli UTXO creati a quel prezzo
- **Heatmap**: Mostra "zone di supporto/resistenza" on-chain

**Interpretazione**:
- **Cluster densi**: Grandi accumuli a un certo prezzo → supporto/resistenza forte
- **Zone vuote**: Pochi UTXO → prezzo passa velocemente
- **Migrazioni**: UTXO che si spostano da un prezzo all'altro (vendite/acquisti)

**Caso d'uso**: Support/Resistance on-chain, costo base holders

---

## 🏗️ Architettura Dati Necessaria

### Dati Richiesti per MVRV

Per calcolare Realized Cap serve:

```sql
-- Per ogni UTXO nel set:
SELECT
    utxo_id,
    amount_btc,
    created_at_block,
    created_at_timestamp,
    price_usd_when_created,  -- ← KEY: Prezzo BTC/USD al momento della creazione
    current_price_usd
FROM utxo_set
WHERE spent = FALSE;

-- Realized Cap = SUM(amount_btc × price_usd_when_created)
-- Market Cap = SUM(amount_btc) × current_price_usd
```

**Problema**: Serve **storico prezzi** per ogni blocco!

---

### Dati Richiesti per URPD

```sql
-- Distribuzione UTXO per realized price:
SELECT
    price_bucket,  -- Es. $50k-$51k
    date,
    SUM(amount_btc) as btc_in_bucket
FROM utxo_set
WHERE spent = FALSE
GROUP BY price_bucket, date
ORDER BY date, price_bucket;
```

**Output**: Time-series matrix per heatmap

---

## 🔍 Cosa Serve Tecnicamente?

### 1. UTXO Set Completo con Metadata

**Fonte dati**: Electrs + Bitcoin Core

```rust
// Electrs espone UTXO queries:
// GET /address/:address/utxo
// Ritorna:
{
    "txid": "...",
    "vout": 0,
    "value": 100000000,  // satoshi
    "status": {
        "confirmed": true,
        "block_height": 850000,
        "block_time": 1698765432
    }
}
```

**Limitazione**: Electrs NON traccia automaticamente "realized price"!

---

### 2. Storico Prezzi BTC/USD per Ogni Blocco

**Fonti possibili**:
- **CoinGecko API**: Storico prezzi giornalieri (rate limit)
- **Binance API**: Candlestick data (più granulare)
- **UTXOracle**: I nostri 672 giorni di prezzi validati! ✅

**Mapping**:
```python
# Per ogni blocco, serve prezzo BTC/USD
block_prices = {
    850000: 67234.50,  # USD/BTC al blocco 850000
    850001: 67245.80,
    ...
}
```

**Problema**: Serve **enrichment** del dataset UTXO con prezzi.

---

### 3. Database Time-Series per Performance

**Schema Database** (PostgreSQL + TimescaleDB):

```sql
-- Tabella principale: UTXO snapshot storico
CREATE TABLE utxo_historical (
    utxo_id BIGSERIAL PRIMARY KEY,
    txid TEXT NOT NULL,
    vout INTEGER NOT NULL,
    amount_sat BIGINT NOT NULL,
    amount_btc DECIMAL(16,8) NOT NULL,
    created_block_height INTEGER NOT NULL,
    created_timestamp TIMESTAMPTZ NOT NULL,
    spent_block_height INTEGER,  -- NULL se unspent
    spent_timestamp TIMESTAMPTZ,
    -- Enrichment
    price_usd_created DECIMAL(12,2) NOT NULL,  -- ← KEY
    realized_value_usd DECIMAL(18,2) NOT NULL,  -- amount_btc × price_usd_created
    address TEXT,
    script_type TEXT,  -- P2PKH, P2WPKH, P2SH, etc.
    cohort TEXT  -- STH (Short-Term), LTH (Long-Term)
);

-- Indice per query veloci
CREATE INDEX idx_created_height ON utxo_historical(created_block_height);
CREATE INDEX idx_spent_height ON utxo_historical(spent_block_height);
CREATE INDEX idx_price_bucket ON utxo_historical(price_usd_created);

-- Tabella aggregata: URPD time-series
CREATE TABLE urpd_daily (
    date DATE NOT NULL,
    price_bucket_min DECIMAL(12,2) NOT NULL,
    price_bucket_max DECIMAL(12,2) NOT NULL,
    btc_supply DECIMAL(16,8) NOT NULL,
    utxo_count INTEGER NOT NULL,
    PRIMARY KEY (date, price_bucket_min)
);

-- Tabella aggregata: MVRV daily
CREATE TABLE mvrv_daily (
    date DATE NOT NULL PRIMARY KEY,
    market_cap_usd DECIMAL(18,2) NOT NULL,
    realized_cap_usd DECIMAL(18,2) NOT NULL,
    mvrv_ratio DECIMAL(10,4) NOT NULL,
    mvrv_sth DECIMAL(10,4) NOT NULL,  -- Short-Term Holders only
    mvrv_lth DECIMAL(10,4) NOT NULL   -- Long-Term Holders only
);
```

**Dimensioni stimate**:
- ~100M UTXO attuali × 200 bytes = **20GB** (snapshot attuale)
- Storico completo (tutti UTXO ever) = **~500GB** (dal 2009)
- Aggregati giornalieri = **~100MB** (leggeri)

---

## 🔄 Pipeline ETL Necessaria

### Step 1: Extract UTXO Set + Blocchi

```python
# Pseudo-code pipeline
import electrum
import requests

def extract_utxo_snapshot(block_height):
    """Estrai UTXO set completo a un certo blocco"""
    # Via electrs API o Bitcoin Core RPC
    utxos = []
    # Query tutte le tx del blocco
    block = bitcoin_rpc.getblock(block_hash)
    for tx in block['tx']:
        tx_data = bitcoin_rpc.getrawtransaction(tx, True)
        for vout in tx_data['vout']:
            utxos.append({
                'txid': tx,
                'vout': vout['n'],
                'amount_btc': vout['value'],
                'created_block': block_height,
                'created_timestamp': block['time'],
                'address': vout['scriptPubKey'].get('address'),
                'script_type': vout['scriptPubKey']['type']
            })
    return utxos

def enrich_with_price(utxos, block_height):
    """Aggiungi prezzo BTC/USD al momento della creazione"""
    price = get_price_at_block(block_height)  # Da UTXOracle o CoinGecko
    for utxo in utxos:
        utxo['price_usd_created'] = price
        utxo['realized_value_usd'] = utxo['amount_btc'] * price
    return utxos
```

---

### Step 2: Track UTXO Spent Status

```python
def mark_spent_utxos(current_block):
    """Marca UTXO spesi nel blocco corrente"""
    block = bitcoin_rpc.getblock(block_hash)
    for tx in block['tx']:
        tx_data = bitcoin_rpc.getrawtransaction(tx, True)
        # Ogni input spende un UTXO precedente
        for vin in tx_data['vin']:
            prev_txid = vin['txid']
            prev_vout = vin['vout']
            # Update DB: mark as spent
            db.execute("""
                UPDATE utxo_historical
                SET spent_block_height = ?, spent_timestamp = ?
                WHERE txid = ? AND vout = ?
            """, (current_block, block_time, prev_txid, prev_vout))
```

---

### Step 3: Calcola MVRV Giornaliero

```python
def calculate_mvrv_daily(date):
    """Calcola MVRV per un giorno specifico"""
    # Market Cap = Prezzo attuale × Supply totale
    current_price = get_price_at_date(date)
    total_supply = 19_500_000  # BTC (approx)
    market_cap = total_supply * current_price

    # Realized Cap = Somma realized value di tutti UTXO unspent
    realized_cap = db.execute("""
        SELECT SUM(realized_value_usd)
        FROM utxo_historical
        WHERE spent_block_height IS NULL  -- Solo unspent
        AND created_timestamp <= ?
    """, (date,)).fetchone()[0]

    mvrv = market_cap / realized_cap

    # MVRV STH (Short-Term Holders): solo UTXO creati <155 giorni fa
    date_155_days_ago = date - timedelta(days=155)
    realized_cap_sth = db.execute("""
        SELECT SUM(realized_value_usd)
        FROM utxo_historical
        WHERE spent_block_height IS NULL
        AND created_timestamp BETWEEN ? AND ?
    """, (date_155_days_ago, date)).fetchone()[0]

    mvrv_sth = market_cap / realized_cap_sth

    return {'mvrv': mvrv, 'mvrv_sth': mvrv_sth}
```

---

### Step 4: Genera URPD Heatmap Data

```python
def generate_urpd_heatmap(start_date, end_date, bucket_size=1000):
    """Genera dati per heatmap URPD"""
    # Bucket prices (es. $50k-$51k, $51k-$52k, ...)
    price_buckets = list(range(0, 120000, bucket_size))  # $0 - $120k

    heatmap_data = []
    for date in date_range(start_date, end_date):
        for bucket_min in price_buckets:
            bucket_max = bucket_min + bucket_size
            btc_in_bucket = db.execute("""
                SELECT SUM(amount_btc)
                FROM utxo_historical
                WHERE spent_block_height IS NULL  -- Unspent
                AND created_timestamp <= ?
                AND price_usd_created BETWEEN ? AND ?
            """, (date, bucket_min, bucket_max)).fetchone()[0] or 0

            heatmap_data.append({
                'date': date,
                'price_min': bucket_min,
                'price_max': bucket_max,
                'btc_supply': btc_in_bucket
            })

    return heatmap_data
```

---

## ⚡ Sfide Tecniche

### 1. Volume Dati Massiccio
- **Bitcoin blockchain**: ~500GB (full node)
- **UTXO set completo storico**: ~500GB aggiuntivi
- **Query pesanti**: Aggregazioni su milioni di righe

**Soluzione**:
- TimescaleDB per time-series ottimizzate
- Materialized views per aggregati pre-calcolati
- Incremental updates (solo nuovi blocchi)

---

### 2. Tempo di Inizializzazione
- **Full sync da Genesis (2009)**: Giorni/settimane di processing
- **Enrichment con prezzi**: Rate limits API esterne

**Soluzione**:
- Parallelize block processing
- Cache prezzi storici (usa UTXOracle.py output!)
- Start from checkpoint recente (es. ultimi 2 anni)

---

### 3. Real-time Updates
- **Nuovi blocchi ogni 10 min**: Update UTXO set + aggregati
- **Ricalcolo MVRV**: Richiede query su DB completo

**Soluzione**:
- Incremental updates (solo delta blocco)
- Background job per aggregati pesanti
- Cache risultati con TTL

---

## 🎨 Frontend Visualization

### Chart Library Recommendation

**Per URPD Heatmap**:
- **Plotly.js**: Heatmap nativo, interattivo
- **D3.js**: Controllo completo, custom
- **Chart.js + plugin**: Più semplice

**Esempio Plotly.js**:
```javascript
// URPD Heatmap
const data = [{
    x: dates,  // ['2023-01-01', '2023-01-02', ...]
    y: price_buckets,  // [50000, 51000, 52000, ...]
    z: btc_supply_matrix,  // [[100, 200, ...], [150, 180, ...], ...]
    type: 'heatmap',
    colorscale: 'Viridis'
}];

Plotly.newPlot('urpd-chart', data, {
    title: 'UTXO Realized Price Distribution',
    xaxis: { title: 'Date' },
    yaxis: { title: 'Price (USD)' }
});
```

**Per MVRV Line Chart**:
```javascript
// MVRV STH Timeline
const trace = {
    x: dates,
    y: mvrv_sth_values,
    type: 'scatter',
    mode: 'lines',
    line: { color: 'orange', width: 2 }
};

const layout = {
    title: 'MVRV Short-Term Holders',
    yaxis: { title: 'MVRV Ratio' },
    shapes: [
        // Top zone (>2.0)
        { type: 'rect', y0: 2, y1: 5, fillcolor: 'red', opacity: 0.2 },
        // Bottom zone (<0.8)
        { type: 'rect', y0: 0, y1: 0.8, fillcolor: 'green', opacity: 0.2 }
    ]
};

Plotly.newPlot('mvrv-chart', [trace], layout);
```

---

## 📦 Architettura Completa Proposta

```
┌─────────────────────────────────────────────────────┐
│                BITCOIN FULL NODE                    │
│              + Electrs Indexer                      │
└──────────────────┬──────────────────────────────────┘
                   │
                   v
┌─────────────────────────────────────────────────────┐
│           ETL PIPELINE (Python/Rust)                │
│  ┌────────────────────────────────────────────┐    │
│  │  1. UTXO Extractor (per block)             │    │
│  │     - Read new blocks                      │    │
│  │     - Extract UTXO created/spent           │    │
│  └────────────────────────────────────────────┘    │
│  ┌────────────────────────────────────────────┐    │
│  │  2. Price Enrichment                       │    │
│  │     - Map block → BTC/USD price            │    │
│  │     - Use UTXOracle.py output              │    │
│  └────────────────────────────────────────────┘    │
│  ┌────────────────────────────────────────────┐    │
│  │  3. Aggregation Engine                     │    │
│  │     - Calculate MVRV daily                 │    │
│  │     - Generate URPD buckets                │    │
│  └────────────────────────────────────────────┘    │
└──────────────────┬──────────────────────────────────┘
                   │
                   v
┌─────────────────────────────────────────────────────┐
│     POSTGRESQL + TIMESCALEDB                        │
│  - utxo_historical (raw data)                       │
│  - mvrv_daily (aggregated)                          │
│  - urpd_daily (aggregated)                          │
└──────────────────┬──────────────────────────────────┘
                   │
                   v
┌─────────────────────────────────────────────────────┐
│          FASTAPI QUERY API                          │
│  GET /api/mvrv?range=2024-01-01:2024-12-31         │
│  GET /api/urpd/heatmap?bucket=1000                 │
│  GET /api/utxo/distribution                        │
└──────────────────┬──────────────────────────────────┘
                   │
                   v
┌─────────────────────────────────────────────────────┐
│       FRONTEND DASHBOARD (React/Vue)                │
│  - Plotly.js charts                                 │
│  - Real-time updates (polling/WebSocket)            │
│  - Export data (CSV/JSON)                           │
└─────────────────────────────────────────────────────┘
```

---

## 💰 Stima Complessità

| Component | Tempo | Difficoltà | Dipendenze |
|-----------|-------|------------|------------|
| **Setup Infrastructure** | 2-3 giorni | Media | Full node, electrs, PostgreSQL |
| **ETL Pipeline** | 2-3 settimane | Alta | Bitcoin RPC, elettrs API |
| **Price Enrichment** | 3-5 giorni | Bassa | UTXOracle.py, CoinGecko API |
| **Database Schema** | 2-3 giorni | Media | PostgreSQL, TimescaleDB |
| **Initial Sync** | 1-2 settimane | Alta | Dipende da hardware |
| **Aggregation Queries** | 1 settimana | Media | SQL optimization |
| **FastAPI Backend** | 3-5 giorni | Bassa | Python, FastAPI |
| **Frontend Charts** | 1 settimana | Media | React, Plotly.js |
| **Testing + Validation** | 1 settimana | Media | Compare vs. Glassnode |

**Totale**: **8-12 settimane** (full-time)

**Costo hardware**:
- SSD 2TB: ~$150
- RAM 32GB: Required per initial sync
- CPU: Multi-core per parallelize

---

## 🎯 Approccio Pragmatico: 3 Opzioni

### Option A: Usa API Esistenti (FAST)
**Glassnode / CryptoQuant hanno API**:
- ✅ Dati già pronti
- ✅ No infrastructure overhead
- ❌ Costo: $400-800/mese (premium tier)
- ❌ Dipendenza esterna

**Tempo**: 1-2 settimane (solo frontend)

---

### Option B: Self-Hosted Parziale (MEDIUM)
**Usa dati pre-aggregati** da progetto open-source:
- Bitcoin blockchain analysis toolkit: https://github.com/blockchain-analysis
- Pre-computed UTXO datasets

**Tempo**: 4-6 settimane

---

### Option C: Full Custom (SLOW ma Sovereign)
**Build from scratch** come descritto sopra.

**Tempo**: 8-12 settimane
**Pro**: Controllo completo, no API limits, privacy
**Cons**: Complessità alta, maintenance pesante

---

## 🔑 Risposta alla Tua Domanda

> Occorre estrarre tramite API e salvare in un database?

**Sì, assolutamente!** Per replicare CheckOnChain serve:

1. **Extract**: UTXO set via electrs/Bitcoin Core RPC
2. **Transform**: Enrichment con prezzi storici (UTXOracle!)
3. **Load**: Database time-series (PostgreSQL + TimescaleDB)
4. **Aggregate**: Pre-calcola metriche giornaliere
5. **Serve**: API REST per frontend
6. **Visualize**: Plotly.js/D3.js charts interattivi

**Non si può fare real-time on-the-fly** perché:
- Calcoli troppo pesanti (milioni di UTXO)
- Serve storico (UTXO created 6 mesi fa)
- Aggregazioni richiedono full table scans

**Database è essenziale** per:
- Caching risultati
- Fast queries
- Time-series optimization

---

## 🚀 Raccomandazione

### Per Iniziare Velocemente:

**Phase 1** (2 settimane): **Proof of Concept**
- Usa Glassnode API free tier
- Implementa frontend charts
- Valida se le metriche sono utili per il tuo use case

**Phase 2** (4-6 settimane): **Self-Hosted Light**
- Setup electrs + PostgreSQL
- ETL per ultimi 6 mesi (non full history)
- Pre-compute MVRV + URPD giornalmente

**Phase 3** (8-12 settimane): **Production Full**
- Full historical sync
- Real-time updates
- Ottimizzazioni performance
- Monitoring + alerting

---

## 📝 Next Steps

Vuoi che:

1. **Esploro Glassnode API** per POC veloce?
2. **Setup electrs + PostgreSQL** per self-hosted?
3. **Implemento ETL pipeline** sample per UTXO extraction?
4. **Creo schema database** dettagliato?
5. **Frontend POC** con dati mock?

Dimmi e procedo! 🚀
