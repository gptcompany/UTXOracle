#!/usr/bin/env python3
"""
Health Check Utility
Task T010+: Production-ready health check for monitoring and K8s probes

Provides comprehensive health checks for:
- Database connectivity (DuckDB)
- External services (Electrs HTTP API)
- Memory usage
- System resources

Designed for:
- Kubernetes liveness/readiness probes
- Monitoring systems (Prometheus, Datadog, etc.)
- Load balancer health checks
"""

import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
import time
import psutil
import aiohttp
import duckdb

from scripts.config.mempool_config import get_config

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Overall health status"""

    HEALTHY = "healthy"  # All checks passed
    DEGRADED = "degraded"  # Some non-critical checks failed
    UNHEALTHY = "unhealthy"  # Critical checks failed


@dataclass
class ComponentHealth:
    """Health status for individual component"""

    name: str
    status: HealthStatus
    message: str
    latency_ms: Optional[float] = None
    details: Optional[Dict[str, Any]] = None


class HealthChecker:
    """
    Comprehensive health checker for whale detection system

    Performs checks on:
    - Database (DuckDB)
    - Electrs API
    - Memory usage
    - System resources

    Example:
        checker = HealthChecker()
        health = await checker.check_all()
        if health["status"] == "healthy":
            print("System operational")
    """

    def __init__(self):
        """Initialize health checker with config"""
        self.config = get_config()

    async def check_database(self) -> ComponentHealth:
        """
        Check DuckDB database connectivity

        Returns:
            ComponentHealth with database status
        """
        start_time = time.time()
        try:
            # Open connection and run simple query
            conn = duckdb.connect(self.config.database_path)
            result = conn.execute("SELECT 1 AS health_check").fetchone()
            conn.close()

            latency_ms = (time.time() - start_time) * 1000

            if result and result[0] == 1:
                return ComponentHealth(
                    name="database",
                    status=HealthStatus.HEALTHY,
                    message="Database operational",
                    latency_ms=latency_ms,
                )
            else:
                return ComponentHealth(
                    name="database",
                    status=HealthStatus.UNHEALTHY,
                    message="Database query returned unexpected result",
                    latency_ms=latency_ms,
                )

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(f"Database health check failed: {e}")
            return ComponentHealth(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message=f"Database error: {str(e)}",
                latency_ms=latency_ms,
            )

    async def check_electrs(self) -> ComponentHealth:
        """
        Check Electrs HTTP API connectivity

        Returns:
            ComponentHealth with Electrs status
        """
        start_time = time.time()
        try:
            # Fetch current block height from Electrs
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.config.electrs_http_url}/blocks/tip/height",
                    timeout=aiohttp.ClientTimeout(total=5.0),
                ) as response:
                    latency_ms = (time.time() - start_time) * 1000

                    if response.status == 200:
                        height_text = await response.text()
                        block_height = int(height_text.strip())

                        # Sanity check: block height should be reasonable
                        if block_height > 700000:  # After Bitcoin's ~700k block
                            return ComponentHealth(
                                name="electrs",
                                status=HealthStatus.HEALTHY,
                                message="Electrs API operational",
                                latency_ms=latency_ms,
                                details={"block_height": block_height},
                            )
                        else:
                            return ComponentHealth(
                                name="electrs",
                                status=HealthStatus.DEGRADED,
                                message=f"Electrs returned unusual block height: {block_height}",
                                latency_ms=latency_ms,
                                details={"block_height": block_height},
                            )
                    else:
                        return ComponentHealth(
                            name="electrs",
                            status=HealthStatus.UNHEALTHY,
                            message=f"Electrs returned HTTP {response.status}",
                            latency_ms=latency_ms,
                        )

        except aiohttp.ClientConnectorError as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(f"Electrs connection failed: {e}")
            return ComponentHealth(
                name="electrs",
                status=HealthStatus.UNHEALTHY,
                message=f"Connection error: {str(e)}",
                latency_ms=latency_ms,
            )
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(f"Electrs health check failed: {e}")
            return ComponentHealth(
                name="electrs",
                status=HealthStatus.UNHEALTHY,
                message=f"Electrs error: {str(e)}",
                latency_ms=latency_ms,
            )

    def check_memory(self) -> ComponentHealth:
        """
        Check system memory usage

        Returns:
            ComponentHealth with memory status
        """
        try:
            # Get current process memory
            process = psutil.Process()
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024  # Convert to MB

            # Check against configured limits
            if memory_mb < self.config.memory_warning_threshold_mb:
                status = HealthStatus.HEALTHY
                message = f"Memory usage normal: {memory_mb:.1f} MB"
            elif memory_mb < self.config.max_memory_mb:
                status = HealthStatus.DEGRADED
                message = f"Memory usage elevated: {memory_mb:.1f} MB (warning threshold: {self.config.memory_warning_threshold_mb} MB)"
            else:
                status = HealthStatus.UNHEALTHY
                message = f"Memory usage critical: {memory_mb:.1f} MB (max: {self.config.max_memory_mb} MB)"

            return ComponentHealth(
                name="memory",
                status=status,
                message=message,
                details={
                    "memory_mb": round(memory_mb, 2),
                    "warning_threshold_mb": self.config.memory_warning_threshold_mb,
                    "max_memory_mb": self.config.max_memory_mb,
                    "percent": round((memory_mb / self.config.max_memory_mb) * 100, 1),
                },
            )

        except Exception as e:
            logger.error(f"Memory health check failed: {e}")
            return ComponentHealth(
                name="memory",
                status=HealthStatus.DEGRADED,
                message=f"Memory check error: {str(e)}",
            )

    async def check_all(self) -> Dict[str, Any]:
        """
        Run all health checks

        Returns:
            Dictionary with overall status and component details:
            {
                "status": "healthy" | "degraded" | "unhealthy",
                "timestamp": <ISO timestamp>,
                "components": {
                    "database": {...},
                    "electrs": {...},
                    "memory": {...}
                },
                "summary": {
                    "healthy_count": 3,
                    "degraded_count": 0,
                    "unhealthy_count": 0
                }
            }
        """
        import datetime

        # Run all checks
        db_health = await self.check_database()
        electrs_health = await self.check_electrs()
        memory_health = self.check_memory()

        components = {
            "database": {
                "status": db_health.status,
                "message": db_health.message,
                "latency_ms": db_health.latency_ms,
                "details": db_health.details,
            },
            "electrs": {
                "status": electrs_health.status,
                "message": electrs_health.message,
                "latency_ms": electrs_health.latency_ms,
                "details": electrs_health.details,
            },
            "memory": {
                "status": memory_health.status,
                "message": memory_health.message,
                "details": memory_health.details,
            },
        }

        # Count statuses
        statuses = [db_health.status, electrs_health.status, memory_health.status]
        healthy_count = sum(1 for s in statuses if s == HealthStatus.HEALTHY)
        degraded_count = sum(1 for s in statuses if s == HealthStatus.DEGRADED)
        unhealthy_count = sum(1 for s in statuses if s == HealthStatus.UNHEALTHY)

        # Determine overall status
        if unhealthy_count > 0:
            overall_status = HealthStatus.UNHEALTHY
        elif degraded_count > 0:
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY

        return {
            "status": overall_status,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "components": components,
            "summary": {
                "healthy_count": healthy_count,
                "degraded_count": degraded_count,
                "unhealthy_count": unhealthy_count,
                "total_count": len(statuses),
            },
        }


# Example usage and testing
if __name__ == "__main__":
    import asyncio
    import json

    async def test_health_checks():
        print("🏥 Health Check System Test")
        print("=" * 60)

        checker = HealthChecker()

        # Test 1: Individual component checks
        print("\n📊 Individual Component Checks:")

        print("\n1. Database check:")
        db_health = await checker.check_database()
        print(f"   Status: {db_health.status}")
        print(f"   Message: {db_health.message}")
        print(f"   Latency: {db_health.latency_ms:.2f}ms")

        print("\n2. Electrs check:")
        electrs_health = await checker.check_electrs()
        print(f"   Status: {electrs_health.status}")
        print(f"   Message: {electrs_health.message}")
        print(f"   Latency: {electrs_health.latency_ms:.2f}ms")
        if electrs_health.details:
            print(f"   Block Height: {electrs_health.details.get('block_height')}")

        print("\n3. Memory check:")
        memory_health = checker.check_memory()
        print(f"   Status: {memory_health.status}")
        print(f"   Message: {memory_health.message}")
        if memory_health.details:
            print(
                f"   Memory: {memory_health.details['memory_mb']} MB ({memory_health.details['percent']}%)"
            )

        # Test 2: Comprehensive health check
        print("\n\n🔍 Comprehensive Health Check:")
        health = await checker.check_all()

        print(f"\n   Overall Status: {health['status']}")
        print(f"   Timestamp: {health['timestamp']}")
        print("\n   Summary:")
        summary = health["summary"]
        print(f"     ✅ Healthy: {summary['healthy_count']}/{summary['total_count']}")
        print(f"     ⚠️  Degraded: {summary['degraded_count']}/{summary['total_count']}")
        print(
            f"     ❌ Unhealthy: {summary['unhealthy_count']}/{summary['total_count']}"
        )

        print("\n   Components:")
        for name, component in health["components"].items():
            icon = (
                "✅"
                if component["status"] == "healthy"
                else "⚠️"
                if component["status"] == "degraded"
                else "❌"
            )
            print(f"     {icon} {name}: {component['message']}")

        # Test 3: JSON output (for API)
        print("\n\n📄 JSON Output (API format):")
        print(json.dumps(health, indent=2))

        # Test 4: HTTP status code mapping
        print("\n\n🌐 HTTP Status Code Mapping:")
        status_codes = {
            HealthStatus.HEALTHY: 200,
            HealthStatus.DEGRADED: 200,  # Still operational
            HealthStatus.UNHEALTHY: 503,  # Service unavailable
        }
        http_status = status_codes[health["status"]]
        print(f"   Health Status: {health['status']}")
        print(f"   HTTP Status Code: {http_status}")

        print("\n✅ Health check system test completed!")

    # Run tests
    asyncio.run(test_health_checks())
