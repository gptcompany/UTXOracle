# TODO: Downsampling Analysis & Implementation Plan

**Context**: UTXOracle.py usa un filtro dinamico per ridurre ~100k intraday prices → ~24k punti per HTML visualization. Vogliamo riutilizzare questa logica per serie storiche 2023-2025.

**Status**: 📋 PLANNING PHASE
**Created**: Nov 2, 2025
**Priority**: MEDIUM (future feature, not blocking)

---

## Phase 1: Reverse Engineering - Capire il Downsampling Attuale ⏳

### 1.1 Analisi Algoritmo Corrente
- [ ] **T201**: Analizzare UTXOracle.py linee 1351-1407 (ax_range calculation + filtering)
  - Capire formula: `ax_range = 0.05 + (dev_pct - 0.17) * map_dev_axr`
  - Trovare valore `map_dev_axr`
  - Range: 5% min, 20% max

- [ ] **T202**: Quantificare riduzione dati su esempi reali
  - Contare `output_prices` totali (pre-filtering)
  - Contare `prices` array (post-filtering)
  - Calcolare % riduzione per 5 date diverse
  - Formula: `reduction_pct = (1 - filtered/total) * 100`

- [ ] **T203**: Analizzare distribuzione temporale
  - I punti sono uniformemente distribuiti nel tempo?
  - O sono concentrati dove c'è più volatilità?
  - Verificare con `heights_smooth` e `timestamps` arrays

### 1.2 Misurazioni Concrete
- [ ] **T204**: Script per misurare downsampling esistente
  ```python
  # Script: scripts/measure_downsampling.py
  # Input: Una data (es: 2025-10-24)
  # Output:
  #   - Total intraday outputs: 34,867
  #   - Filtered for chart: 23,956 (31% reduction)
  #   - ax_range used: 0.053 (±5.3%)
  #   - Price range: $105k-$116k
  ```

- [ ] **T205**: Confronta con date diverse (alta/bassa volatilità)
  - Bassa volatilità: ax_range ~ 5% → riduzione ~20%
  - Alta volatilità: ax_range ~ 20% → riduzione ~60%

---

## Phase 2: Design - Downsampling per Serie Storiche 📐

### 2.1 Requisiti Funzionali
- [ ] **T206**: Definire use case
  - **Use Case 1**: Single-date chart (già implementato in HTML)
  - **Use Case 2**: Multi-date series (2023-2025, ~730 date)
  - **Use Case 3**: Real-time dashboard (ultimi 30 giorni)

- [ ] **T207**: Calcolare data size senza downsampling
  - 730 date × 30k punti/date = **21.9M punti**
  - Canvas 2D limit: ~1M punti (performance degrada dopo)
  - Target: ridurre a **<500k punti totali**
  - **Riduzione necessaria**: 97.7% (43× compression)

### 2.2 Strategie di Downsampling

#### Opzione A: Adaptive Price Range (come UTXOracle.py)
- [ ] **T208**: Adattare `ax_range` per multi-date
  ```python
  # Per ogni data:
  # 1. Calcola central_price e deviation
  # 2. Applica ax_range (5-20% dinamico)
  # 3. Filtra punti fuori range
  # Pro: Mantiene più dati dove c'è volatilità
  # Contro: Numero punti variabile per data
  ```

#### Opzione B: Fixed Sample Rate
- [ ] **T209**: Sample fisso per date
  ```python
  # Riduzione uniforme:
  # - 730 date × 685 punti/date = 500k punti
  # - Sample rate: ~43 punti ogni 1000 (4.3%)
  # Pro: Numero punti prevedibile
  # Contro: Perde dettagli su date volatili
  ```

#### Opzione C: Temporal Aggregation
- [ ] **T210**: Aggregazione temporale intelligente
  ```python
  # Sliding window:
  # - Aggregare punti vicini nel tempo
  # - Mantenere min/max/avg per ogni finestra
  # - Simile a candlestick chart
  # Pro: Riduzione efficace + mantiene trend
  # Contro: Più complesso da implementare
  ```

#### Opzione D: Hybrid Approach
- [ ] **T211**: Combinare strategie
  ```python
  # Multi-level sampling:
  # 1. Price range filter (ax_range) → 50% reduction
  # 2. Temporal aggregation → 50% reduction
  # 3. Total: 75% reduction
  # Pro: Bilanciato tra qualità e dimensione
  # Contro: Complessità implementativa
  ```

### 2.3 API Design
- [ ] **T212**: Design API per library
  ```python
  # Proposta 1: Metodo separato
  def downsample_for_visualization(
      self,
      prices: List[float],
      timestamps: List[int],
      target_points: int = 1000,
      method: str = "adaptive"  # "adaptive", "fixed", "temporal", "hybrid"
  ) -> Dict[str, List]:
      """
      Riduce punti per visualizzazione mantenendo trend.

      Returns:
          {
              "prices": [...],
              "timestamps": [...],
              "reduction_pct": 97.5,
              "method_used": "adaptive"
          }
      """

  # Proposta 2: Flag in calculate_price_for_transactions
  result = calc.calculate_price_for_transactions(
      transactions,
      return_intraday=True,
      downsample=True,
      target_points=1000
  )
  ```

---

## Phase 3: Proof of Concept 🧪

### 3.1 Implementazione Minimal
- [ ] **T213**: Implementare Opzione B (Fixed Sample Rate) come POC
  - File: `UTXOracle_library.py` nuovo metodo `_downsample_fixed()`
  - Test: 5 date random, verifica riduzione ~95%
  - Output: JSON con `{prices, timestamps, blocks}`

- [ ] **T214**: Test su serie 2023-2025
  - Generare serie completa (730 date)
  - Applicare downsampling
  - Misurare:
    * Tempo processamento
    * Dimensione JSON output
    * Quality metrics (trend preservation)

### 3.2 Benchmark & Validazione
- [ ] **T215**: Confronta strategie A, B, C
  - Metriche:
    * Reduction ratio
    * Trend preservation (correlation con original)
    * Edge case handling (spike detection)
    * Performance (ms/date)

- [ ] **T216**: Definire "good enough" threshold
  - Correlation > 0.99 con dati originali?
  - Max spike miss: <5%?
  - Performance: <100ms per 730 date?

---

## Phase 4: Integration Options 🔌

### 4.1 Backend Integration (FastAPI)
- [ ] **T217**: Endpoint per historical data downsampled
  ```python
  @app.get("/api/prices/historical-chart")
  async def get_historical_chart(
      start_date: str,
      end_date: str,
      max_points: int = 1000
  ):
      # 1. Query DuckDB per date range
      # 2. Applica downsampling
      # 3. Return JSON compatto
  ```

- [ ] **T218**: Caching strategy
  - Cache downsampled data per range comune
  - Invalidazione: daily (nuovi dati)
  - Storage: Redis o DuckDB materialized view

### 4.2 Frontend Integration (Canvas 2D)
- [ ] **T219**: Adattare `frontend/comparison.html`
  - Fetch da nuovo endpoint
  - Render con Plotly.js o Canvas 2D
  - Toggle: "Show all data" vs "Optimized view"

- [ ] **T220**: Progressive loading
  - Carica overview (1000 punti) subito
  - Load on-demand: zoom → fetch più dettagli

---

## Phase 5: Alternative Approaches 💡

### 5.1 Database-Level Aggregation
- [ ] **T221**: DuckDB window functions
  ```sql
  -- Pre-compute aggregated views
  CREATE TABLE price_analysis_5min AS
  SELECT
    date,
    floor(extract(epoch from timestamp) / 300) * 300 as ts_bucket,
    avg(price_usd) as avg_price,
    min(price_usd) as min_price,
    max(price_usd) as max_price,
    count(*) as sample_count
  FROM intraday_prices
  GROUP BY date, ts_bucket;
  ```

### 5.2 External Libraries
- [ ] **T222**: Valutare librerie esistenti
  - `scipy.signal.resample()` - Signal resampling
  - `pandas.DataFrame.resample()` - Time series resampling
  - `downsample` library - Pure Python downsampling
  - Visvalingam-Whyatt algorithm - Line simplification

### 5.3 WebAssembly Optimization
- [ ] **T223**: Port algoritmo in Rust/WASM
  - Compile a WASM per frontend
  - Downsampling nel browser (client-side)
  - Pro: Zero backend load
  - Contro: Complessità deployment

---

## Decision Matrix 🎯

| Approach | Complexity | Performance | Quality | Maintainability |
|----------|-----------|-------------|---------|-----------------|
| **Adaptive Price Range** | Medium | Fast | High | Medium |
| **Fixed Sample Rate** | Low | Very Fast | Medium | High |
| **Temporal Aggregation** | High | Medium | High | Medium |
| **Hybrid** | High | Medium | Very High | Low |
| **Database-Level** | Medium | Very Fast | High | High |
| **External Library** | Low | Fast | High | High |

**Raccomandazione Preliminare**:
1. **Short-term (MVP)**: Fixed Sample Rate (T213)
2. **Medium-term**: Database-Level Aggregation (T221)
3. **Long-term**: Hybrid Approach + Caching (T211 + T218)

---

## Open Questions ❓

1. **Performance Budget**: Quanto tempo possiamo spendere per downsampling?
   - <10ms = Inline durante query
   - <100ms = Acceptable con caching
   - >100ms = Pre-compute required

2. **Data Granularity**: Serve zoom-in dettagliato?
   - Yes → Progressive loading (T220)
   - No → Single-level downsampling sufficiente

3. **Real-time Updates**: Dashboard aggiornato ogni 10min?
   - Yes → Incremental downsampling
   - No → Batch processing OK

4. **Multi-Resolution**: Serve downsampling diverso per zoom levels?
   - Yes → Tile-based approach (come mappe)
   - No → Single resolution OK

---

## Success Criteria ✅

**Must Have**:
- [ ] Serie 2023-2025 (730 date) renders in <2s
- [ ] Output size <5MB JSON
- [ ] Trend preservation >95% correlation

**Nice to Have**:
- [ ] Interactive zoom preserva spike detection
- [ ] Real-time updates <100ms latency
- [ ] Works on mobile (Canvas memory <50MB)

---

## Next Steps for New Session 🚀

1. **T201-T205**: Analizzare & misurare downsampling esistente (1h)
2. **T206-T212**: Design API e strategie (1h)
3. **T213-T214**: POC con Fixed Sample Rate (2h)
4. **Decision Point**: Scegliere approccio basato su risultati POC

**Estimated Total**: 8-12 hours development + testing
