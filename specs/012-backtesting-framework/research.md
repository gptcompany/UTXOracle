# Research: Backtesting Framework

**Feature**: spec-012 | **Date**: 2025-12-04 | **Status**: Complete

## Research Topics

### 1. Backtesting Methodology

**Decision**: Walk-forward validation with expanding window

**Rationale**:
- **Walk-forward**: Train on [t-N, t], test on [t, t+M], slide forward
- **Prevents look-ahead bias**: Only uses data available at decision time
- **More realistic**: Mimics real trading conditions

**Alternatives Considered**:
| Method | Pros | Cons |
|--------|------|------|
| Simple train/test split | Fast | Doesn't capture temporal dynamics |
| K-fold cross-validation | Standard | Violates temporal ordering |
| **Walk-forward (chosen)** | Realistic | Computationally heavier |

### 2. Performance Metrics

**Decision**: Sharpe, Sortino, Win Rate, Max Drawdown, Profit Factor

**Formulas**:

```python
# Sharpe Ratio (annualized)
sharpe = (mean(returns) - rf) / std(returns) * sqrt(252)

# Sortino Ratio (downside risk only)
sortino = (mean(returns) - rf) / std(negative_returns) * sqrt(252)

# Win Rate
win_rate = count(positive_trades) / count(all_trades)

# Max Drawdown
max_dd = min(cumulative_return - running_peak)

# Profit Factor
profit_factor = sum(positive_pnl) / abs(sum(negative_pnl))
```

### 3. Trade Signal Logic

**Decision**: Threshold-based with configurable levels

```python
DEFAULT_BUY_THRESHOLD = 0.3   # signal > 0.3 → BUY
DEFAULT_SELL_THRESHOLD = -0.3  # signal < -0.3 → SELL
# else → HOLD
```

### 4. Transaction Costs

**Decision**: 0.1% per trade (configurable)

**Rationale**: Includes spread (~0.05%) + exchange fees (~0.05%)

## Technical Findings

### Data Sources

1. **Primary**: DuckDB `prices` table
   - Fields: timestamp, utxoracle_price, exchange_price, confidence
   - 672+ days of historical data

2. **Fallback**: `historical_data/html_files/`
   - Parse HTML files for UTXOracle prices
   - Use for dates not in DuckDB

### Performance Estimates

| Operation | Time | Memory |
|-----------|------|--------|
| Load 365 days | ~1s | ~50MB |
| Simulate 100 trades | ~10ms | ~1MB |
| Calculate all metrics | ~5ms | ~1MB |
| Grid search (100 configs) | ~30s | ~100MB |
| **Total 365-day backtest** | **<60s** | **<200MB** |

## Conclusions

1. **Methodology**: Walk-forward validation prevents overfitting
2. **Metrics**: Standard quant finance set (Sharpe, Sortino, DD, WR, PF)
3. **Signals**: Simple threshold crossing (easily extended)
4. **Data**: DuckDB primary, HTML fallback
5. **Performance**: Well within 60s target

**Ready for Phase 1 design.**
