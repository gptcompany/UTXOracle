# Research: Cointime Economics Framework

**Spec**: spec-018
**Date**: 2025-12-06

---

## R1: Coinblocks Definition

### Source
ARK Invest + Glassnode White Paper (2023)

### Formula

**Coinblocks Created**:
```
For each UTXO held:
  coinblocks_created += btc_value × 1 (per block)

Cumulative: Σ(btc_value × blocks_held)
```

**Coinblocks Destroyed**:
```
When UTXO is spent:
  coinblocks_destroyed = btc_value × (spend_block - creation_block)
```

### Example
- 1 BTC created at block 800,000
- Spent at block 800,100
- Coinblocks destroyed = 1 × 100 = 100

---

## R2: Liveliness & Vaultedness

### Liveliness
```
Liveliness = Cumulative_Destroyed / Cumulative_Created
```

- Range: 0 to 1
- High (>0.4): Active network, coins moving
- Low (<0.2): Dormant network, hodling

### Vaultedness
```
Vaultedness = 1 - Liveliness
```

- Inverse of Liveliness
- Measures network inactivity

---

## R3: Supply Metrics

### Active Supply
```
Active_Supply = Total_Supply × Liveliness
```

### Vaulted Supply
```
Vaulted_Supply = Total_Supply × Vaultedness
```

### Interpretation
- Active Supply: BTC that has moved "recently" (weighted by activity)
- Vaulted Supply: BTC that has remained dormant

---

## R4: Valuation Metrics

### True Market Mean
```
True_Market_Mean = Market_Cap / Active_Supply
```

- Price if only active supply matters
- Higher than spot price during accumulation
- Lower during distribution

### AVIV Ratio
```
AVIV = Current_Price / True_Market_Mean
```

- Activity-adjusted MVRV
- Superior to standard MVRV (accounts for dormancy)

### Interpretation
| AVIV | Zone | Meaning |
|------|------|---------|
| <0.8 | Undervalued | Accumulation zone |
| 0.8-1.2 | Fair | Normal market |
| 1.2-2.0 | Warming | Caution |
| >2.0 | Overheated | Distribution risk |

---

## R5: Advantages over HODL Waves

| Aspect | HODL Waves | Cointime |
|--------|-----------|----------|
| Assumption | "Old = hodling" | None |
| Input | Age bands | Math only |
| Subjectivity | High | Zero |
| Academic rigor | Heuristic | Formal |

---

## Summary

| Concept | Formula | Use |
|---------|---------|-----|
| Coinblocks Created | BTC × blocks | Accumulation measure |
| Coinblocks Destroyed | BTC × age | Activity measure |
| Liveliness | Destroyed/Created | Network activity |
| AVIV | Price / TMM | Valuation |
