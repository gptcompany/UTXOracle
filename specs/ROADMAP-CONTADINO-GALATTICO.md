# Roadmap: Contadino Galattico Implementation

**Created**: 2025-12-06
**Based On**: `archive/contadino_galattico.md` (42 sources, 7 peer-reviewed)
**Methodology**: Evidence-based ranking with empirical validation

---

## Executive Summary

Questa roadmap implementa la visione **Contadino Galattico**: un approccio evidence-based che priorizza metriche con validazione empirica su quelle puramente teoriche.

### Cambiamenti Chiave

| Aspetto | Prima (Intuition) | Dopo (Evidence-Based) |
|---------|-------------------|----------------------|
| Funding Rate | 15% weight | 5% (LAGGING) |
| Whale Signal | 25% weight | 15% (Grade D) |
| STH/LTH SOPR | Non implementato | 15% (82.44% accuracy) |
| Wasserstein | 0/54 tasks | IN CORSO (Grade A) |

### Proiezione Accuracy

```
Baseline (spec-009):          ████████████████████░░░░░░░░░░ 65%
+ spec-010 Wasserstein:       ██████████████████████░░░░░░░░ 70% (+5%)
+ spec-014 Fix Weights:       ██████████████████████░░░░░░░░ 71% (+1%)
+ spec-016 STH/LTH SOPR:      █████████████████████████████░ 82% (+11%)
+ spec-017/018 Cointime:      ██████████████████████████████ 85%+ (+3%)
```

---

## Implementation Phases

### Phase 1: Quick Wins (1-2 settimane)

| Spec | Feature | Effort | Impact |
|------|---------|--------|--------|
| **spec-010** | Wasserstein Distance | 3-5 giorni | +5% accuracy |
| **spec-014** | Fix Fusion Weights | 1-2 giorni | +1% accuracy |
| **spec-015** | Backtest Validation | 2-3 giorni | Validation data |

**Status**: spec-010 IN CORSO

**Deliverables**:
- Wasserstein distance calculator con regime detection
- Evidence-based weight configuration
- Validation reports per spec-009 metrics

---

### Phase 2: High-Impact Metrics (2-3 settimane)

| Spec | Feature | Effort | Impact |
|------|---------|--------|--------|
| **spec-016** | STH/LTH SOPR | 2-3 settimane | +11% accuracy |

**Why High Priority**:
- **Grade A-B evidence**: 82.44% accuracy (Omole & Enke 2024)
- **Leading indicator**: STH-SOPR predicts price
- **Partial implementation**: Non richiede full UTXO set

**Deliverables**:
- SOPR calculation from spent outputs
- STH/LTH cohort classification (155-day threshold)
- Signal generation (capitulation, break-even cross)
- Fusion integration (9th component)

---

### Phase 3: Foundation (4-6 settimane)

| Spec | Feature | Effort | Impact |
|------|---------|--------|--------|
| **spec-017** | UTXO Lifecycle Engine | 4-6 settimane | Foundation |

**Why Foundation**:
Abilita TUTTE le metriche Tier A:
- MVRV, Realized Cap, NUPL
- HODL Waves
- Cointime Economics
- Entity-adjusted metrics

**Phased Implementation**:
1. **6-month history** (MVP): STH metrics, recent SOPR
2. **2-year history** (Optional): Full LTH metrics
3. **Full history** (Optional): Complete HODL Waves

---

### Phase 4: Advanced Framework (3-4 settimane)

| Spec | Feature | Effort | Impact |
|------|---------|--------|--------|
| **spec-018** | Cointime Economics | 3-4 settimane | +2-3% accuracy |

**Why Important**:
- **Grade A evidence**: ARK + Glassnode White Paper
- **No heuristics**: Pure mathematical framework
- **Superior to MVRV**: AVIV ratio con activity-weighting

---

## Spec Dependency Graph

```
spec-009 (Done) ──┬─► spec-010 (In Progress) ─► spec-014 (Fix Weights)
                  │
                  └─► spec-015 (Backtest) ─► Validation Reports

spec-013 (Done) ──► spec-016 (SOPR) ──► spec-017 (UTXO Lifecycle)
                                                    │
                                                    └─► spec-018 (Cointime)
```

---

## Evidence-Based Tier Ranking

### TIER S - Implement Now (Score >80)

| # | Feature | Evidence | Score | Status |
|---|---------|----------|-------|--------|
| 1 | **Wasserstein Distance** | A | 86 | spec-010 IN CORSO |
| 2 | **STH/LTH SOPR** | A-B | 90 | spec-016 DRAFT |
| 3 | **Entity-Adjusted** | A | 80 | spec-013 DONE |

### TIER A - High Priority (Score 50-70)

| # | Feature | Evidence | Score | Status |
|---|---------|----------|-------|--------|
| 4 | Cointime Economics | A | 62 | spec-018 DRAFT |
| 5 | MVRV dinamico | B | 59 | Requires spec-017 |
| 6 | Realized Cap | A | 55 | Requires spec-017 |

### TIER B - Moderate Priority (Score 25-50)

| # | Feature | Evidence | Score | Status |
|---|---------|----------|-------|--------|
| 7 | Puell Multiple | B→C | 38 | Mining metrics declining |
| 8 | Hash Ribbons | B→C | 38 | Mining metrics declining |

### TIER R - Research (Validation Needed)

| # | Feature | Evidence | Status |
|---|---------|----------|--------|
| 9 | Symbolic Dynamics | C | spec-015 will validate |
| 10 | Fractal Dimension | C | spec-015 will validate |
| 11 | Power Law | C | spec-015 will validate |

---

## What NOT to Implement

Based on evidence analysis:

| Feature | Evidence | Reason |
|---------|----------|--------|
| Mempool Whale (high weight) | D | Zero empirical validation |
| Funding Rate (high weight) | B-LAGGING | "Trailing byproduct" - Coinbase |
| Technical Indicators | N/A | Derived from price, circular |
| Static MVRV thresholds | Failed | Need dynamic adaptation |

---

## Success Metrics

### Per-Phase Goals

| Phase | Goal | Metric |
|-------|------|--------|
| 1 | Validated metrics | Backtest reports complete |
| 2 | SOPR integration | Sharpe improvement >0 |
| 3 | UTXO lifecycle | 6-month history indexed |
| 4 | Cointime | Full framework operational |

### Overall Target

- **Accuracy**: 65% → 85%+ (+20%)
- **Evidence Grade**: Majority Grade A-B metrics
- **Validation**: All metrics with statistical significance

---

## Resource Estimates

| Phase | Effort | Timeline |
|-------|--------|----------|
| Phase 1 | 1-2 settimane | Immediate |
| Phase 2 | 2-3 settimane | Post Phase 1 |
| Phase 3 | 4-6 settimane | Post Phase 2 |
| Phase 4 | 3-4 settimane | Post Phase 3 |
| **Total** | **~3-4 mesi** | Full implementation |

---

## Files Created

```
specs/
├── 014-evidence-based-weights/
│   └── spec.md              # Fix fusion weights
├── 015-backtest-validation/
│   └── spec.md              # Validate spec-009 metrics
├── 016-sth-lth-sopr/
│   └── spec.md              # SOPR implementation
├── 017-utxo-lifecycle-engine/
│   └── spec.md              # Foundation for advanced metrics
├── 018-cointime-economics/
│   └── spec.md              # ARK/Glassnode framework
└── ROADMAP-CONTADINO-GALATTICO.md  # This file
```

---

## References

- `archive/contadino_galattico.md` - Evidence-based analysis
- `archive/contadino_cosmico.md` - Original vision
- `archive/contadino_cosmico_post_lettura.md` - Ultra-KISS revision
- `research/on-chain-metrics-empirical-analysis.md` - Full research
- `research/EXECUTIVE_SUMMARY.md` - Quick reference

---

*Roadmap generata il 2025-12-06*
*Basata su analisi di 42 fonti (7 peer-reviewed, 15 industry research)*
