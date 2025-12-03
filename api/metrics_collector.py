"""
Performance Metrics Collector - Task T053
Collects latency, throughput, and error rate metrics for API endpoints

Features:
- Request/response timing
- Endpoint-specific metrics
- Throughput tracking (requests per second)
- Error rate monitoring
- Rolling window statistics
- KISS principle: In-memory storage, no external dependencies

Usage:
    from api.metrics_collector import MetricsCollector, metrics_middleware

    collector = MetricsCollector()
    app = FastAPI()
    app.middleware("http")(metrics_middleware(collector))

    @app.get("/metrics")
    async def get_metrics():
        return collector.get_metrics()
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Deque
from collections import deque, defaultdict
from threading import Lock
from fastapi import Request

logger = logging.getLogger(__name__)


@dataclass
class RequestMetric:
    """Single request metric"""

    timestamp: float
    endpoint: str
    method: str
    status_code: int
    duration_ms: float
    success: bool


@dataclass
class EndpointStats:
    """Statistics for a specific endpoint"""

    total_requests: int = 0
    total_errors: int = 0
    total_duration_ms: float = 0.0
    min_duration_ms: float = float("inf")
    max_duration_ms: float = 0.0
    recent_requests: Deque[float] = field(default_factory=lambda: deque(maxlen=100))

    def add_request(self, duration_ms: float, is_error: bool):
        """Add a request to statistics"""
        self.total_requests += 1
        if is_error:
            self.total_errors += 1

        self.total_duration_ms += duration_ms
        self.min_duration_ms = min(self.min_duration_ms, duration_ms)
        self.max_duration_ms = max(self.max_duration_ms, duration_ms)
        self.recent_requests.append(time.time())

    def get_avg_duration_ms(self) -> float:
        """Calculate average duration"""
        if self.total_requests == 0:
            return 0.0
        return self.total_duration_ms / self.total_requests

    def get_error_rate(self) -> float:
        """Calculate error rate percentage"""
        if self.total_requests == 0:
            return 0.0
        return (self.total_errors / self.total_requests) * 100

    def get_recent_throughput(self, window_seconds: int = 60) -> float:
        """Calculate requests per second in recent window"""
        if not self.recent_requests:
            return 0.0

        now = time.time()
        cutoff = now - window_seconds

        # Count requests within window
        recent_count = sum(1 for ts in self.recent_requests if ts >= cutoff)

        return recent_count / window_seconds if window_seconds > 0 else 0.0


class MetricsCollector:
    """
    Collects and aggregates performance metrics

    Example:
        collector = MetricsCollector(max_history=1000)

        # Record a request
        collector.record_request(
            endpoint="/api/prices/latest",
            method="GET",
            status_code=200,
            duration_ms=45.2
        )

        # Get metrics
        metrics = collector.get_metrics()
        print(f"Total requests: {metrics['total_requests']}")
        print(f"Avg latency: {metrics['avg_latency_ms']:.2f}ms")
    """

    def __init__(self, max_history: int = 1000):
        """
        Initialize metrics collector

        Args:
            max_history: Maximum number of requests to keep in history
        """
        self.max_history = max_history
        self.history: Deque[RequestMetric] = deque(maxlen=max_history)
        self.endpoint_stats: Dict[str, EndpointStats] = defaultdict(EndpointStats)
        self.lock = Lock()

        # Global counters
        self.total_requests = 0
        self.total_errors = 0
        self.start_time = time.time()

        logger.info(f"Metrics collector initialized (max_history={max_history})")

    def record_request(
        self, endpoint: str, method: str, status_code: int, duration_ms: float
    ):
        """
        Record a request metric

        Args:
            endpoint: API endpoint path
            method: HTTP method (GET, POST, etc.)
            status_code: HTTP response status code
            duration_ms: Request duration in milliseconds
        """
        is_error = status_code >= 400

        with self.lock:
            # Create metric record
            metric = RequestMetric(
                timestamp=time.time(),
                endpoint=endpoint,
                method=method,
                status_code=status_code,
                duration_ms=duration_ms,
                success=not is_error,
            )

            # Add to history
            self.history.append(metric)

            # Update global counters
            self.total_requests += 1
            if is_error:
                self.total_errors += 1

            # Update endpoint-specific stats
            endpoint_key = f"{method} {endpoint}"
            self.endpoint_stats[endpoint_key].add_request(duration_ms, is_error)

    def get_metrics(self, window_seconds: int = 60) -> dict:
        """
        Get aggregated metrics

        Args:
            window_seconds: Time window for throughput calculation (default: 60)

        Returns:
            dict: Aggregated metrics including latency, throughput, error rates
        """
        with self.lock:
            if self.total_requests == 0:
                return {
                    "total_requests": 0,
                    "total_errors": 0,
                    "error_rate_percent": 0.0,
                    "uptime_seconds": time.time() - self.start_time,
                    "avg_latency_ms": 0.0,
                    "min_latency_ms": 0.0,
                    "max_latency_ms": 0.0,
                    "throughput_rps": 0.0,
                    "endpoints": {},
                }

            # Calculate global stats from history
            durations = [m.duration_ms for m in self.history]
            avg_latency = sum(durations) / len(durations) if durations else 0.0
            min_latency = min(durations) if durations else 0.0
            max_latency = max(durations) if durations else 0.0

            # Calculate throughput (recent window)
            now = time.time()
            cutoff = now - window_seconds
            recent_requests = sum(1 for m in self.history if m.timestamp >= cutoff)
            throughput = recent_requests / window_seconds if window_seconds > 0 else 0.0

            # Build endpoint metrics
            endpoint_metrics = {}
            for endpoint_key, stats in self.endpoint_stats.items():
                endpoint_metrics[endpoint_key] = {
                    "total_requests": stats.total_requests,
                    "total_errors": stats.total_errors,
                    "error_rate_percent": round(stats.get_error_rate(), 2),
                    "avg_duration_ms": round(stats.get_avg_duration_ms(), 2),
                    "min_duration_ms": round(stats.min_duration_ms, 2)
                    if stats.min_duration_ms != float("inf")
                    else 0.0,
                    "max_duration_ms": round(stats.max_duration_ms, 2),
                    "recent_throughput_rps": round(
                        stats.get_recent_throughput(window_seconds), 2
                    ),
                }

            return {
                "total_requests": self.total_requests,
                "total_errors": self.total_errors,
                "error_rate_percent": round(
                    (self.total_errors / self.total_requests * 100), 2
                ),
                "uptime_seconds": round(now - self.start_time, 2),
                "avg_latency_ms": round(avg_latency, 2),
                "min_latency_ms": round(min_latency, 2),
                "max_latency_ms": round(max_latency, 2),
                "throughput_rps": round(throughput, 2),
                "endpoints": endpoint_metrics,
                "window_seconds": window_seconds,
            }

    def reset_stats(self):
        """Reset all statistics"""
        with self.lock:
            self.history.clear()
            self.endpoint_stats.clear()
            self.total_requests = 0
            self.total_errors = 0
            self.start_time = time.time()
            logger.info("Metrics collector stats reset")


def metrics_middleware(collector: MetricsCollector):
    """
    FastAPI middleware for automatic metrics collection

    Usage:
        from api.metrics_collector import MetricsCollector, metrics_middleware

        collector = MetricsCollector()
        app = FastAPI()
        app.middleware("http")(metrics_middleware(collector))
    """

    async def middleware(request: Request, call_next):
        # Skip metrics endpoint itself to avoid recursion
        if request.url.path == "/metrics":
            return await call_next(request)

        # Record start time
        start_time = time.time()

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000

        # Record metric
        collector.record_request(
            endpoint=request.url.path,
            method=request.method,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        return response

    return middleware


# Global metrics collector instance (optional - can be created per-app)
_global_collector = None


def get_global_collector() -> MetricsCollector:
    """Get or create global metrics collector instance"""
    global _global_collector
    if _global_collector is None:
        _global_collector = MetricsCollector()
    return _global_collector


# Example usage
if __name__ == "__main__":
    from fastapi import FastAPI
    import uvicorn
    import random

    # Create collector
    collector = MetricsCollector()

    # Create app
    app = FastAPI()

    # Add metrics middleware
    app.middleware("http")(metrics_middleware(collector))

    @app.get("/test")
    async def test_endpoint():
        # Simulate variable latency
        import asyncio

        await asyncio.sleep(random.uniform(0.01, 0.1))

        # Simulate occasional errors
        if random.random() < 0.1:  # 10% error rate
            raise Exception("Simulated error")

        return {"status": "ok"}

    @app.get("/metrics")
    async def get_metrics():
        return collector.get_metrics(window_seconds=60)

    print("Starting test server on http://localhost:8080/test")
    print("Metrics available at http://localhost:8080/metrics")
    print("\nTry:")
    print("  curl http://localhost:8080/test  # Make requests")
    print("  curl http://localhost:8080/metrics | jq  # View metrics")

    uvicorn.run(app, host="127.0.0.1", port=8080)
