# Research & Technical Decisions

**Feature**: Real-time Mempool Whale Detection
**Date**: 2025-11-07
**Phase**: 0 - Research & Resolution

## Executive Summary

All technical unknowns have been resolved through analysis of existing infrastructure and clarification during specification phase. The feature will reuse existing mempool.space WebSocket API, WhaleFlowDetector classification logic, and dashboard infrastructure with minimal new dependencies.

## Technical Decisions

### 1. WebSocket Library Selection

**Decision**: Use `websockets` library (pure Python implementation)

**Rationale**:
- Pure Python, no C extensions required
- Built-in reconnection support with exponential backoff
- Async/await native support
- Well-maintained (10+ years), stable API
- Already used in similar Bitcoin projects

**Alternatives Considered**:
- `aiohttp`: More heavyweight, includes HTTP client/server (unnecessary)
- `python-socketio`: Adds Socket.IO protocol overhead we don't need
- Raw `asyncio` sockets: Too low-level, requires reimplementing reconnection logic

### 2. Memory Management Strategy

**Decision**: Streaming architecture with bounded collections (deque with maxlen)

**Rationale**:
- Python's `collections.deque(maxlen=N)` automatically drops oldest items
- O(1) append/pop operations
- Memory-bounded by design
- Simple to implement 400MB threshold checks

**Alternatives Considered**:
- Redis for transaction cache: Adds external dependency, violates KISS principle
- SQLite for temporary storage: Disk I/O overhead for real-time stream
- Unbounded lists: Risk of memory exhaustion during congestion

### 3. Transaction Data Source

**Decision**: mempool.space WebSocket endpoint `/ws/track-mempool-tx`

**Rationale**:
- Already running locally (ws://localhost:8999)
- Provides full transaction data including fee rates
- Zero additional infrastructure
- Maintained by mempool.space team

**Alternatives Considered**:
- Direct Bitcoin Core ZMQ: Would duplicate existing mempool.space work
- REST API polling: Too slow for <1 second requirement
- Custom mempool indexer: Massive complexity increase

### 4. Urgency Score Calculation

**Decision**: Linear interpolation based on fee percentiles

**Rationale**:
- Simple formula: `urgency = min(1.0, fee_rate / high_priority_threshold)`
- Uses mempool.space fee estimates API for thresholds
- Adjusts dynamically with market conditions
- RBF reduces confidence by 20% (multiply by 0.8)

**Alternatives Considered**:
- Machine learning model: Overengineering for initial version
- Fixed thresholds: Breaks during fee market volatility
- Block template prediction: Too complex, requires full mempool state

### 5. Alert Distribution Architecture

**Decision**: WebSocket broadcast to dashboard + optional webhooks

**Rationale**:
- WebSocket for real-time dashboard updates
- Webhooks for external integrations
- Future Redis pub/sub channel for NautilusTrader
- No message queue initially (YAGNI)

**Alternatives Considered**:
- Server-Sent Events (SSE): One-way only, no bidirectional communication
- Long polling: Inefficient for real-time streams
- gRPC streaming: Adds protobuf complexity

### 6. Prediction Storage

**Decision**: DuckDB for 90-day retention

**Rationale**:
- Already used in daily_analysis.py
- Embedded database, no server required
- Efficient time-series queries
- Automatic old data cleanup with date-based partitioning

**Alternatives Considered**:
- PostgreSQL: Requires separate server
- InfluxDB: Time-series specific but adds new dependency
- CSV files: Poor query performance for correlation analysis

### 7. RBF Transaction Handling

**Decision**: Update existing prediction with "modified" flag

**Rationale**:
- Maintains prediction continuity
- Preserves original timestamp for correlation
- Clear audit trail of changes
- Prevents duplicate alerts

**Alternatives Considered**:
- New prediction for each replacement: Causes alert spam
- Ignore replacements: Loses important fee escalation signals
- Keep all versions: Unnecessary complexity

### 8. Performance Optimization

**Decision**: Process transactions in micro-batches (100ms windows)

**Rationale**:
- Reduces WhaleFlowDetector invocations
- Amortizes classification overhead
- Still meets <1 second latency requirement
- Natural aggregation for burst traffic

**Alternatives Considered**:
- Process individually: Higher CPU overhead
- Large batches (1 second): Too close to latency limit
- Parallel processing: Complexity without clear benefit at current scale

## Integration Points

### Existing Components to Reuse

1. **WhaleFlowDetector** (`scripts/whale_flow_detector.py`)
   - Methods: `classify_transaction()`, `_load_exchange_addresses()`
   - No modifications needed, used as-is

2. **mempool.space Docker Stack**
   - WebSocket endpoint: `ws://localhost:8999/ws/track-mempool-tx`
   - Fee estimates API: `http://localhost:8999/api/v1/fees/recommended`
   - Already running, no configuration changes

3. **Dashboard** (`frontend/comparison.html`)
   - Add new `<div id="mempool-predictions">` section
   - Reuse existing Plotly.js charts
   - Extend WebSocket connection logic

4. **DuckDB Integration** (`scripts/daily_analysis.py`)
   - Reuse connection setup and table patterns
   - Add `mempool_predictions` table
   - Share database file location

## Best Practices

### WebSocket Resilience

```python
# Exponential backoff reconnection
async def connect_with_retry(url, max_retries=5):
    for attempt in range(max_retries):
        try:
            return await websockets.connect(url)
        except Exception as e:
            wait_time = min(2 ** attempt, 30)  # Cap at 30 seconds
            await asyncio.sleep(wait_time)
    raise ConnectionError(f"Failed to connect after {max_retries} attempts")
```

### Memory Pressure Handling

```python
# Check memory usage before processing
def check_memory_pressure():
    import psutil
    process = psutil.Process()
    memory_mb = process.memory_info().rss / 1024 / 1024

    if memory_mb > 400:  # 80% of 500MB limit
        # Start dropping low-fee transactions
        return True
    return False
```

### Correlation Tracking

```python
# Track prediction outcomes
CREATE TABLE mempool_predictions (
    prediction_id TEXT PRIMARY KEY,
    transaction_id TEXT NOT NULL,
    predicted_flow TEXT NOT NULL,
    btc_value REAL NOT NULL,
    fee_rate REAL NOT NULL,
    urgency_score REAL NOT NULL,
    prediction_time TIMESTAMP NOT NULL,
    confirmation_time TIMESTAMP,
    actual_outcome TEXT,
    was_modified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for correlation queries
CREATE INDEX idx_prediction_time ON mempool_predictions(prediction_time);
CREATE INDEX idx_confirmation_time ON mempool_predictions(confirmation_time);
```

## Risk Mitigations

### Technical Risks

1. **WebSocket Instability**
   - Mitigation: Exponential backoff reconnection
   - Fallback: Continue confirmed-only analysis

2. **Memory Exhaustion**
   - Mitigation: Bounded collections, 400MB threshold
   - Fallback: Drop low-fee transactions

3. **RBF Alert Spam**
   - Mitigation: Update existing predictions
   - Flag as "modified" for transparency

### Performance Risks

1. **High Transaction Volume**
   - Mitigation: Micro-batching (100ms windows)
   - Monitoring: Log processing latency

2. **Classification Bottleneck**
   - Mitigation: Reuse WhaleFlowDetector instance
   - Cache exchange address lookups

## Validation Strategy

### Unit Testing
- Mock WebSocket connection
- Test urgency score calculations
- Verify memory pressure handling

### Integration Testing
- Test with real mempool.space WebSocket
- Verify WhaleFlowDetector integration
- End-to-end alert flow

### Performance Testing
- Simulate 1000 tx/minute stream
- Measure detection latency
- Monitor memory usage

## Next Steps

1. Generate data models (Phase 1)
2. Create API contracts (Phase 1)
3. Update quickstart documentation
4. Proceed to task generation (`/speckit.tasks`)

---

**Research Complete**: All technical decisions finalized, ready for implementation.