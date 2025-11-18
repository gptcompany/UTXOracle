# Polish Plan - P2 Enhancements
**Date**: 2025-11-14
**Goal**: Production-grade polish (1-2 days)
**Status**: In Progress

---

## 📋 Task Breakdown

### Task 1: Enhanced /health Endpoint ⏱️ 2-3 hours
**Status**: ✅ COMPLETE

#### Implemented Features
✅ Database connectivity check with latency tracking
✅ Uptime tracking
✅ Gap detection (last 7 days)
✅ electrs HTTP API connectivity check (`http://localhost:3001`)
✅ mempool.space backend connectivity check (`http://localhost:8999`)
✅ Timestamp tracking (current + last_success per service)
✅ Service-specific status (ok/error/timeout per service)
✅ Overall status determination (healthy/degraded/unhealthy)
✅ Backward compatibility maintained

#### Implementation Plan

**Step 1.1**: Expand HealthStatus Model
```python
class HealthStatus(BaseModel):
    """Enhanced API health check response"""
    status: str  # healthy, degraded, unhealthy
    timestamp: datetime
    uptime_seconds: float
    started_at: str

    # Services
    checks: Dict[str, ServiceCheck] = {}

    # Legacy fields (backward compatibility)
    database: str
    gaps_detected: Optional[int] = None
    missing_dates: Optional[List[str]] = None

class ServiceCheck(BaseModel):
    """Individual service health check"""
    status: str  # ok, error, timeout
    latency_ms: Optional[float] = None
    error: Optional[str] = None
    last_success: Optional[str] = None
```

**Step 1.2**: Add Connectivity Check Helpers
```python
async def check_electrs_connectivity() -> ServiceCheck:
    """Check electrs HTTP API connectivity"""
    try:
        start = time.time()
        response = await asyncio.wait_for(
            aiohttp.get("http://localhost:3001/blocks/tip/height"),
            timeout=2.0
        )
        latency = (time.time() - start) * 1000

        if response.status == 200:
            return ServiceCheck(
                status="ok",
                latency_ms=round(latency, 2),
                last_success=datetime.utcnow().isoformat()
            )
        else:
            return ServiceCheck(
                status="error",
                error=f"HTTP {response.status}"
            )
    except asyncio.TimeoutError:
        return ServiceCheck(status="error", error="timeout")
    except Exception as e:
        return ServiceCheck(status="error", error=str(e))

async def check_mempool_backend() -> ServiceCheck:
    """Check mempool.space backend API connectivity"""
    try:
        start = time.time()
        response = await asyncio.wait_for(
            aiohttp.get("http://localhost:8999/api/v1/prices"),
            timeout=2.0
        )
        latency = (time.time() - start) * 1000

        if response.status == 200:
            return ServiceCheck(
                status="ok",
                latency_ms=round(latency, 2),
                last_success=datetime.utcnow().isoformat()
            )
        else:
            return ServiceCheck(
                status="error",
                error=f"HTTP {response.status}"
            )
    except asyncio.TimeoutError:
        return ServiceCheck(status="error", error="timeout")
    except Exception as e:
        return ServiceCheck(status="error", error=str(e))
```

**Step 1.3**: Update /health Endpoint
```python
@app.get("/health", response_model=HealthStatus)
async def health_check():
    """
    Comprehensive health check with service connectivity.

    Checks:
    - Database (DuckDB) connectivity
    - electrs HTTP API availability
    - mempool.space backend API availability
    - Data freshness (gap detection)

    Returns:
        HealthStatus: Detailed health status
    """
    uptime = (datetime.utcnow() - STARTUP_TIME).total_seconds()
    checks = {}

    # Existing database check (with enhancements)
    db_check = await check_database_connectivity()
    checks["database"] = db_check

    # NEW: electrs connectivity
    electrs_check = await check_electrs_connectivity()
    checks["electrs"] = electrs_check

    # NEW: mempool.space backend
    mempool_check = await check_mempool_backend()
    checks["mempool_backend"] = mempool_check

    # Determine overall status
    if all(c.status == "ok" for c in checks.values()):
        overall_status = "healthy"
    elif any(c.status == "error" for c in ["database"]):
        overall_status = "unhealthy"  # Critical service down
    else:
        overall_status = "degraded"  # Non-critical service issues

    return HealthStatus(
        status=overall_status,
        timestamp=datetime.utcnow(),
        uptime_seconds=uptime,
        started_at=STARTUP_TIME.isoformat(),
        checks=checks,
        # Backward compatibility
        database=checks["database"].status,
        gaps_detected=gaps_count if gaps_count > 0 else None,
        missing_dates=gaps if gaps else None
    )
```

**Estimated Time**: 2-3 hours

---

### Task 2: Structured Logging with correlation_id ⏱️ 4-6 hours
**Status**: ✅ COMPLETE

#### Implemented Features
✅ structlog library installed (>=23.2.0)
✅ JSON output configured for production
✅ Correlation ID middleware implemented
✅ Context enrichment with correlation_id
✅ Helper function `get_logger()` available
✅ Automatic X-Correlation-ID header injection
✅ Graceful fallback to standard logging if import fails
✅ Modular design (separate logging_config.py module)

#### Implementation Plan

**Step 2.1**: Install Dependencies
```bash
pip install structlog
# Or add to requirements.txt:
# structlog==23.2.0
```

**Step 2.2**: Configure structlog
```python
import structlog

# Configure structlog for production
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()  # JSON for production
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)
```

**Step 2.3**: Add Correlation ID Middleware
```python
from starlette.middleware.base import BaseHTTPMiddleware
import uuid

class CorrelationIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())

        # Add to request state
        request.state.correlation_id = correlation_id

        # Add to structlog context
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        response = await call_next(request)

        # Add to response headers
        response.headers["X-Correlation-ID"] = correlation_id

        # Clear context
        structlog.contextvars.clear_contextvars()

        return response

# Add to app
app.add_middleware(CorrelationIDMiddleware)
```

**Step 2.4**: Update Logging Patterns
```python
# Before (generic):
logger.error(f"Failed to process transaction: {e}")

# After (structured with context):
logger.error(
    "transaction_processing_failed",
    txid=tx_data["txid"],
    btc_value=tx_data["btc_value"],
    error=str(e),
    client_ip=request.client.host,
    correlation_id=request.state.correlation_id,
    exc_info=True
)
```

**Estimated Time**: 4-6 hours

---

### Task 3: Test Coverage 76% → 80% ⏱️ 8-10 hours
**Status**: ⏳ PENDING

#### Current Status
✅ Integration tests: 70% (14/20 passing)
✅ Orchestrator tests: 100% (12/12 passing)
⚠️ Overall coverage: 76.5% (26/34 tests passing)

#### Target
🎯 80% test coverage (error paths + edge cases)

#### Implementation Plan

**Step 3.1**: Identify Untested Error Paths
```bash
# Run coverage report
pytest --cov=scripts --cov=api --cov-report=html

# Identify missing coverage:
# - Database offline scenarios
# - Malformed JWT tokens
# - Invalid mempool data
# - Cache eviction edge cases
# - Concurrent WebSocket connections
# - Token expiration during active session
```

**Step 3.2**: Write Error Path Tests
```python
# Example: Database offline
def test_price_endpoint_handles_db_offline(client, monkeypatch):
    """GET /api/prices/latest should return 503 when DB is offline"""
    def mock_get_db_connection():
        raise Exception("Database connection failed")

    monkeypatch.setattr("api.main.get_db_connection", mock_get_db_connection)

    response = client.get("/api/prices/latest")
    assert response.status_code == 503
    assert "Database connection failed" in response.json()["detail"]

# Example: Malformed JWT
def test_auth_rejects_malformed_jwt(client):
    """Auth middleware should reject malformed JWT tokens"""
    response = client.get(
        "/api/prices/latest",
        headers={"Authorization": "Bearer INVALID_TOKEN"}
    )
    assert response.status_code == 401
    assert "Invalid or expired token" in response.json()["detail"]

# Example: Invalid mempool data
def test_transaction_processor_handles_invalid_data(processor):
    """Processor should handle malformed transaction data"""
    invalid_tx = {"txid": "abc", "btc_value": "NOT_A_NUMBER"}
    result = processor.process(invalid_tx)
    assert result is None  # Should fail gracefully
    assert processor.stats["parse_errors"] == 1
```

**Step 3.3**: Add Concurrent Scenario Tests
```python
import asyncio
import pytest

@pytest.mark.asyncio
async def test_websocket_handles_concurrent_connections():
    """Broadcaster should handle multiple concurrent WebSocket connections"""
    async with create_test_clients(count=10) as clients:
        # All clients connect simultaneously
        await asyncio.gather(*[c.connect() for c in clients])

        # Broadcast message
        await broadcaster.send_whale_alert(test_alert)

        # All clients should receive
        for client in clients:
            message = await client.receive()
            assert message["type"] == "whale_alert"
```

**Estimated Time**: 8-10 hours

---

## 📈 Progress Tracking

| Task | Status | Time Estimate | Time Spent | Completion |
|------|--------|---------------|------------|------------|
| Enhanced /health | ✅ COMPLETE | 2-3 hours | 2h | 100% |
| Structured logging | ✅ COMPLETE | 4-6 hours | 4h | 100% |
| Test coverage → 80% | ⏳ PENDING | 8-10 hours | 0h | 0% |

**Total Estimated**: 14-19 hours (~2 days)
**Progress**: 2/3 tasks complete (67%)

---

## 🎯 Success Criteria

**Task 1 Complete When**:
- ✅ /health endpoint checks electrs connectivity
- ✅ /health endpoint checks mempool.space backend
- ✅ ServiceCheck model with latency tracking
- ✅ Overall status correctly determined from service checks
- ✅ Backward compatibility maintained

**Task 2 Complete When**:
- ✅ structlog installed and configured
- ✅ JSON output in production mode
- ✅ correlation_id in all logs
- ✅ Custom exceptions with context
- ✅ Request/response logging middleware

**Task 3 Complete When**:
- ✅ Test coverage ≥ 80%
- ✅ All error paths tested
- ✅ Edge cases covered
- ✅ Concurrent scenarios tested
- ✅ All 34 tests passing

---

## 📝 Notes

**Why These 3 Tasks?**
- Gemini identified these as P2 enhancements (not blockers)
- They improve production-grade quality without being critical
- They add observability and reliability
- They demonstrate engineering maturity

**After Completion**:
- System will be **production-grade** (not just production-ready)
- Enhanced monitoring and debugging capabilities
- Higher confidence in stability and reliability
- Ready for Phase 4 or immediate deployment

---

**Status**: 🔄 Task 1 in progress - Enhanced /health endpoint
