"""
Memory Pressure Handler - Task T051
Monitors memory usage and triggers graceful degradation at configured thresholds

Architecture:
- WARNING threshold (400MB): Reduce cache sizes, slow down processing
- CRITICAL threshold (500MB): Aggressive cleanup, alert administrators
- RECOVERY threshold (350MB): Resume normal operations

Usage:
    handler = MemoryPressureHandler(warning_mb=400, critical_mb=500)

    async def main_loop():
        while True:
            # Check memory every iteration
            action = await handler.check_and_act()

            if action == PressureAction.CRITICAL:
                # Aggressive cleanup
                await cleanup_caches()
                await notify_admin()
            elif action == PressureAction.WARNING:
                # Reduce resource usage
                reduce_cache_sizes()
"""

import asyncio
import logging
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Callable, Awaitable
from datetime import datetime

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logging.warning("psutil not available - memory pressure handling disabled")

logger = logging.getLogger(__name__)


class PressureLevel(Enum):
    """Memory pressure severity levels"""

    NORMAL = "normal"  # Below warning threshold
    WARNING = "warning"  # Above 400MB (default)
    CRITICAL = "critical"  # Above 500MB (default)
    RECOVERY = "recovery"  # Recovering from warning/critical


class PressureAction(Enum):
    """Actions to take at each pressure level"""

    NONE = "none"  # No action needed
    REDUCE = "reduce"  # Reduce resource usage (WARNING)
    CLEANUP = "cleanup"  # Aggressive cleanup (CRITICAL)
    RECOVER = "recover"  # Resume normal operations


@dataclass
class MemorySnapshot:
    """Memory usage snapshot"""

    timestamp: datetime
    rss_mb: float  # Resident Set Size (actual RAM used)
    vms_mb: float  # Virtual Memory Size
    percent: float  # % of total system memory
    available_mb: float  # Available system memory
    pressure_level: PressureLevel


class MemoryPressureHandler:
    """
    Monitor memory usage and trigger actions at configured thresholds

    Features:
    - Configurable WARNING and CRITICAL thresholds
    - Hysteresis to prevent thrashing (RECOVERY threshold)
    - Callback registration for pressure level changes
    - Periodic monitoring with async/await support
    - Statistics tracking (time in each level, peak usage)
    """

    def __init__(
        self,
        warning_mb: float = 400.0,
        critical_mb: float = 500.0,
        recovery_mb: float = 350.0,
        check_interval_seconds: float = 10.0,
    ):
        """
        Initialize memory pressure handler

        Args:
            warning_mb: WARNING threshold in megabytes (default: 400MB)
            critical_mb: CRITICAL threshold in megabytes (default: 500MB)
            recovery_mb: RECOVERY threshold in megabytes (default: 350MB)
            check_interval_seconds: How often to check memory (default: 10s)
        """
        self.warning_mb = warning_mb
        self.critical_mb = critical_mb
        self.recovery_mb = recovery_mb
        self.check_interval = check_interval_seconds

        self.current_level = PressureLevel.NORMAL
        self.previous_level = PressureLevel.NORMAL

        # Statistics
        self.peak_usage_mb = 0.0
        self.level_durations = {level: 0.0 for level in PressureLevel}
        self.level_enter_time: Optional[datetime] = None
        self.total_warnings = 0
        self.total_criticals = 0

        # Callbacks: Dict[PressureLevel, List[Callable]]
        self.callbacks = {level: [] for level in PressureLevel}

        # Last snapshot
        self.last_snapshot: Optional[MemorySnapshot] = None

        if not PSUTIL_AVAILABLE:
            logger.warning("psutil not available - memory pressure handling disabled")

    def get_memory_snapshot(self) -> Optional[MemorySnapshot]:
        """Get current memory usage snapshot"""
        if not PSUTIL_AVAILABLE:
            return None

        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            system_memory = psutil.virtual_memory()

            rss_mb = memory_info.rss / 1024 / 1024
            vms_mb = memory_info.vms / 1024 / 1024
            available_mb = system_memory.available / 1024 / 1024

            # Determine pressure level
            if rss_mb >= self.critical_mb:
                level = PressureLevel.CRITICAL
            elif rss_mb >= self.warning_mb:
                level = PressureLevel.WARNING
            elif (
                rss_mb <= self.recovery_mb
                and self.current_level != PressureLevel.NORMAL
            ):
                level = PressureLevel.RECOVERY
            else:
                level = PressureLevel.NORMAL

            snapshot = MemorySnapshot(
                timestamp=datetime.now(),
                rss_mb=round(rss_mb, 2),
                vms_mb=round(vms_mb, 2),
                percent=system_memory.percent,
                available_mb=round(available_mb, 2),
                pressure_level=level,
            )

            # Update peak
            if rss_mb > self.peak_usage_mb:
                self.peak_usage_mb = rss_mb

            self.last_snapshot = snapshot
            return snapshot

        except Exception as e:
            logger.error(f"Failed to get memory snapshot: {e}")
            return None

    def _update_level_duration(self):
        """Update duration statistics for current pressure level"""
        if self.level_enter_time:
            duration = (datetime.now() - self.level_enter_time).total_seconds()
            self.level_durations[self.current_level] += duration

    def _transition_level(self, new_level: PressureLevel):
        """Handle transition to new pressure level"""
        if new_level == self.current_level:
            return

        # Update duration for old level
        self._update_level_duration()

        # Log transition
        logger.info(
            f"Memory pressure transition: {self.current_level.value} → {new_level.value} "
            f"(RSS: {self.last_snapshot.rss_mb:.1f}MB)"
        )

        # Update statistics
        if new_level == PressureLevel.WARNING:
            self.total_warnings += 1
        elif new_level == PressureLevel.CRITICAL:
            self.total_criticals += 1

        # Update state
        self.previous_level = self.current_level
        self.current_level = new_level
        self.level_enter_time = datetime.now()

        # Trigger callbacks
        for callback in self.callbacks.get(new_level, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback(self.last_snapshot))
                else:
                    callback(self.last_snapshot)
            except Exception as e:
                logger.error(f"Callback error for {new_level.value}: {e}")

    def check_and_act(self) -> PressureAction:
        """
        Check memory pressure and return recommended action

        Returns:
            PressureAction: Action to take based on current pressure level
        """
        snapshot = self.get_memory_snapshot()
        if not snapshot:
            return PressureAction.NONE

        # Update level if changed
        if snapshot.pressure_level != self.current_level:
            self._transition_level(snapshot.pressure_level)

        # Determine action
        if self.current_level == PressureLevel.CRITICAL:
            return PressureAction.CLEANUP
        elif self.current_level == PressureLevel.WARNING:
            return PressureAction.REDUCE
        elif self.current_level == PressureLevel.RECOVERY:
            return PressureAction.RECOVER
        else:
            return PressureAction.NONE

    async def monitor_loop(self):
        """
        Continuous monitoring loop (run as background task)

        Usage:
            handler = MemoryPressureHandler()
            asyncio.create_task(handler.monitor_loop())
        """
        logger.info(
            f"Memory pressure monitoring started "
            f"(WARNING: {self.warning_mb}MB, CRITICAL: {self.critical_mb}MB)"
        )

        while True:
            try:
                action = self.check_and_act()

                if action != PressureAction.NONE:
                    logger.info(
                        f"Memory pressure action: {action.value} "
                        f"(Level: {self.current_level.value}, "
                        f"RSS: {self.last_snapshot.rss_mb:.1f}MB)"
                    )

            except Exception as e:
                logger.error(f"Memory monitoring error: {e}")

            await asyncio.sleep(self.check_interval)

    def register_callback(
        self,
        level: PressureLevel,
        callback: Callable[[MemorySnapshot], Awaitable[None]],
    ):
        """
        Register callback for pressure level changes

        Args:
            level: Pressure level to trigger callback
            callback: Async function to call with MemorySnapshot

        Example:
            async def on_warning(snapshot: MemorySnapshot):
                logger.warning(f"Memory pressure WARNING: {snapshot.rss_mb}MB")
                reduce_cache_sizes()

            handler.register_callback(PressureLevel.WARNING, on_warning)
        """
        self.callbacks[level].append(callback)

    def get_stats(self) -> dict:
        """Get memory pressure statistics"""
        # Update current level duration
        self._update_level_duration()

        return {
            "current_level": self.current_level.value,
            "current_rss_mb": self.last_snapshot.rss_mb if self.last_snapshot else None,
            "peak_usage_mb": round(self.peak_usage_mb, 2),
            "total_warnings": self.total_warnings,
            "total_criticals": self.total_criticals,
            "level_durations_seconds": {
                level.value: round(duration, 1)
                for level, duration in self.level_durations.items()
            },
            "thresholds": {
                "warning_mb": self.warning_mb,
                "critical_mb": self.critical_mb,
                "recovery_mb": self.recovery_mb,
            },
        }


# Example usage and integration helpers
async def example_usage():
    """Example demonstrating MemoryPressureHandler usage"""
    handler = MemoryPressureHandler(
        warning_mb=400.0,
        critical_mb=500.0,
        recovery_mb=350.0,
        check_interval_seconds=10.0,
    )

    # Register callbacks
    async def on_warning(snapshot: MemorySnapshot):
        logger.warning(f"⚠️  Memory WARNING: {snapshot.rss_mb:.1f}MB")
        # Reduce cache sizes
        # reduce_transaction_cache_size(500)  # Down from 5000

    async def on_critical(snapshot: MemorySnapshot):
        logger.error(f"🚨 Memory CRITICAL: {snapshot.rss_mb:.1f}MB")
        # Aggressive cleanup
        # clear_expired_transactions()
        # force_garbage_collection()
        # send_admin_alert()

    async def on_recovery(snapshot: MemorySnapshot):
        logger.info(f"✅ Memory RECOVERED: {snapshot.rss_mb:.1f}MB")
        # Resume normal operations
        # restore_transaction_cache_size(5000)

    handler.register_callback(PressureLevel.WARNING, on_warning)
    handler.register_callback(PressureLevel.CRITICAL, on_critical)
    handler.register_callback(PressureLevel.RECOVERY, on_recovery)

    # Start monitoring loop
    monitor_task = asyncio.create_task(handler.monitor_loop())

    # Main application loop
    try:
        while True:
            # Your application logic here
            action = handler.check_and_act()

            if action == PressureAction.CLEANUP:
                # Critical: Do aggressive cleanup
                pass
            elif action == PressureAction.REDUCE:
                # Warning: Reduce resource usage
                pass

            await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("Shutting down...")
        monitor_task.cancel()

        # Print final stats
        stats = handler.get_stats()
        logger.info(f"Memory pressure stats: {stats}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(example_usage())
