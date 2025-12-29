#!/usr/bin/env python3
"""
Accuracy Monitor - Prediction Quality Monitoring and Alerting
Tasks: T042a, T042b - Monitor accuracy with thresholds and operator alerting

Features:
- Real-time accuracy calculation from prediction_outcomes table
- Configurable thresholds (warning: 75%, critical: 70%)
- Operator alerting when accuracy degrades
- Rolling window statistics (hourly, daily, weekly)
- Integration with correlation_tracker

Architecture:
- Periodic accuracy checks (every 5 minutes)
- Multi-window analysis (1h, 24h, 7d)
- Alert deduplication (don't spam on repeated failures)
- Structured logging for operator visibility
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any
from enum import Enum
import sys
import os

# Add parent dirs to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.config.mempool_config import get_config
from scripts.utils.db_retry import with_db_retry

import duckdb

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """Alert severity levels"""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AccuracyMonitor:
    """
    Monitor prediction accuracy and alert operators on degradation

    Tracks accuracy across multiple time windows and alerts when
    thresholds are breached. Prevents alert spam via deduplication.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        check_interval_seconds: int = 300,  # 5 minutes
        warning_threshold: float = 0.75,
        critical_threshold: float = 0.70,
        alert_callback: Optional[callable] = None,
    ):
        """
        Initialize accuracy monitor

        Args:
            db_path: Path to DuckDB database (default: from config)
            check_interval_seconds: Interval between accuracy checks (default: 300s)
            warning_threshold: Accuracy threshold for warnings (default: 0.75)
            critical_threshold: Accuracy threshold for critical alerts (default: 0.70)
            alert_callback: Optional callback function for alerts
        """
        config = get_config()
        self.db_path = db_path or config.database.db_path
        self.check_interval = check_interval_seconds
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self.alert_callback = alert_callback

        # Alert deduplication (window -> last_alert_time)
        self.last_alerts: Dict[str, datetime] = {}
        self.alert_cooldown = timedelta(hours=1)  # Don't spam within 1 hour

        # Statistics tracking
        self.stats = {
            "checks_performed": 0,
            "warnings_sent": 0,
            "critical_alerts_sent": 0,
            "last_check": None,
            "current_accuracy_1h": None,
            "current_accuracy_24h": None,
            "current_accuracy_7d": None,
        }

        # Background task
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False

        logger.info("Accuracy monitor initialized")
        logger.info(f"Database: {self.db_path}")
        logger.info(f"Check interval: {check_interval_seconds}s")
        logger.info(
            f"Thresholds: WARNING={warning_threshold:.0%}, CRITICAL={critical_threshold:.0%}"
        )

    async def start(self):
        """Start accuracy monitoring background task"""
        if self._running:
            logger.warning("Accuracy monitor already running")
            return

        self._running = True
        logger.info("🚀 Starting accuracy monitor...")

        # Run initial check immediately
        await self._check_accuracy()

        # Start background monitoring task
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("✅ Accuracy monitoring started")

    async def stop(self):
        """Stop accuracy monitoring background task"""
        if not self._running:
            return

        logger.info("🛑 Stopping accuracy monitor...")
        self._running = False

        # Cancel background task
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        logger.info("✅ Accuracy monitor stopped")

    async def _monitor_loop(self):
        """Background loop to check accuracy periodically"""
        logger.info("🔍 Starting accuracy monitoring loop...")

        while self._running:
            try:
                await asyncio.sleep(self.check_interval)
                await self._check_accuracy()

            except asyncio.CancelledError:
                logger.info("Monitor loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}", exc_info=True)
                await asyncio.sleep(10)  # Backoff on error

    async def _check_accuracy(self):
        """Check accuracy across multiple time windows and alert if needed"""
        try:
            self.stats["checks_performed"] += 1
            self.stats["last_check"] = datetime.now(timezone.utc)

            # Calculate accuracy for multiple windows
            accuracy_1h = await self._calculate_accuracy(hours=1)
            accuracy_24h = await self._calculate_accuracy(hours=24)
            accuracy_7d = await self._calculate_accuracy(hours=168)

            # Update stats
            self.stats["current_accuracy_1h"] = accuracy_1h["accuracy"]
            self.stats["current_accuracy_24h"] = accuracy_24h["accuracy"]
            self.stats["current_accuracy_7d"] = accuracy_7d["accuracy"]

            # Log current status
            logger.info(
                f"📊 Accuracy: 1h={accuracy_1h['accuracy']:.1%} ({accuracy_1h['sample_size']} samples), "
                f"24h={accuracy_24h['accuracy']:.1%} ({accuracy_24h['sample_size']} samples), "
                f"7d={accuracy_7d['accuracy']:.1%} ({accuracy_7d['sample_size']} samples)"
            )

            # Check thresholds and alert if needed
            for window, accuracy_data in [
                ("1h", accuracy_1h),
                ("24h", accuracy_24h),
                ("7d", accuracy_7d),
            ]:
                await self._check_threshold(window, accuracy_data)

        except Exception as e:
            logger.error(f"Error checking accuracy: {e}", exc_info=True)

    @with_db_retry(max_attempts=3)
    async def _calculate_accuracy(self, hours: int) -> Dict[str, Any]:
        """
        Calculate accuracy for time window

        Args:
            hours: Time window in hours

        Returns:
            Dict with accuracy, sample_size, confirmed, accurate
        """
        try:
            conn = duckdb.connect(self.db_path)

            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

            query = """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN outcome_type = 'confirmed' THEN 1 ELSE 0 END) as confirmed,
                    AVG(CASE WHEN outcome_type = 'confirmed' THEN accuracy ELSE 0 END) as avg_accuracy,
                    SUM(CASE WHEN accuracy >= 0.7 THEN 1 ELSE 0 END) as accurate_predictions
                FROM prediction_outcomes
                WHERE outcome_timestamp >= ?
            """

            result = conn.execute(query, [cutoff]).fetchone()
            conn.close()

            if not result or result[0] == 0:
                # No data for this window
                return {
                    "accuracy": 0.0,
                    "sample_size": 0,
                    "confirmed": 0,
                    "accurate": 0,
                }

            total = result[0]
            confirmed = result[1]
            avg_accuracy = result[2] if result[2] else 0.0
            accurate = result[3]

            return {
                "accuracy": avg_accuracy,
                "sample_size": total,
                "confirmed": confirmed,
                "accurate": accurate,
            }

        except Exception as e:
            logger.error(f"Failed to calculate accuracy: {e}", exc_info=True)
            return {
                "accuracy": 0.0,
                "sample_size": 0,
                "confirmed": 0,
                "accurate": 0,
            }

    async def _check_threshold(self, window: str, accuracy_data: Dict[str, Any]):
        """
        Check if accuracy breaches thresholds and alert

        Args:
            window: Time window name (1h, 24h, 7d)
            accuracy_data: Accuracy statistics
        """
        accuracy = accuracy_data["accuracy"]
        sample_size = accuracy_data["sample_size"]

        # Don't alert with insufficient data
        if sample_size < 10:
            logger.debug(f"Insufficient data for {window}: {sample_size} samples")
            return

        # Check if we should alert (cooldown expired)
        alert_key = f"{window}_threshold"
        should_alert = self._should_alert(alert_key)

        # Check thresholds
        if accuracy < self.critical_threshold:
            # CRITICAL alert
            if should_alert:
                await self._send_alert(
                    level=AlertLevel.CRITICAL,
                    window=window,
                    accuracy=accuracy,
                    sample_size=sample_size,
                    threshold=self.critical_threshold,
                )
                self.last_alerts[alert_key] = datetime.now(timezone.utc)
                self.stats["critical_alerts_sent"] += 1

        elif accuracy < self.warning_threshold:
            # WARNING alert
            if should_alert:
                await self._send_alert(
                    level=AlertLevel.WARNING,
                    window=window,
                    accuracy=accuracy,
                    sample_size=sample_size,
                    threshold=self.warning_threshold,
                )
                self.last_alerts[alert_key] = datetime.now(timezone.utc)
                self.stats["warnings_sent"] += 1

    def _should_alert(self, alert_key: str) -> bool:
        """Check if alert cooldown has expired"""
        if alert_key not in self.last_alerts:
            return True

        last_alert = self.last_alerts[alert_key]
        time_since = datetime.now(timezone.utc) - last_alert

        return time_since >= self.alert_cooldown

    async def _send_alert(
        self,
        level: AlertLevel,
        window: str,
        accuracy: float,
        sample_size: int,
        threshold: float,
    ):
        """
        Send alert to operator

        Args:
            level: Alert severity level
            window: Time window
            accuracy: Current accuracy
            sample_size: Number of samples
            threshold: Threshold that was breached
        """
        # Format alert message
        emoji = "🚨" if level == AlertLevel.CRITICAL else "⚠️"
        message = (
            f"{emoji} ACCURACY ALERT ({level.value.upper()})\n"
            f"Window: {window}\n"
            f"Accuracy: {accuracy:.1%} (threshold: {threshold:.0%})\n"
            f"Sample size: {sample_size}\n"
            f"Timestamp: {datetime.now(timezone.utc).isoformat()}"
        )

        # Log alert
        if level == AlertLevel.CRITICAL:
            logger.critical(message)
        else:
            logger.warning(message)

        # Call custom alert callback if provided
        if self.alert_callback:
            try:
                await self.alert_callback(
                    {
                        "level": level.value,
                        "window": window,
                        "accuracy": accuracy,
                        "sample_size": sample_size,
                        "threshold": threshold,
                        "timestamp": datetime.now(timezone.utc),
                    }
                )
            except Exception as e:
                logger.error(f"Failed to execute alert callback: {e}", exc_info=True)

    def get_stats(self) -> Dict[str, Any]:
        """Get current monitoring statistics"""
        return {
            **self.stats,
            "alert_cooldown_hours": self.alert_cooldown.total_seconds() / 3600,
            "thresholds": {
                "warning": self.warning_threshold,
                "critical": self.critical_threshold,
            },
        }


# T042c: Webhook/Email alert callback
async def example_alert_callback(alert_data: Dict[str, Any]):
    """
    Alert callback with webhook and email support

    Sends accuracy degradation alerts via:
    - Webhook POST (if ALERT_WEBHOOK_URL configured)
    - Email SMTP (if ALERT_EMAIL_TO configured)
    """
    import aiohttp
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    logger.info(f"Alert callback triggered: {alert_data}")

    # Webhook notification
    webhook_url = os.getenv("ALERT_WEBHOOK_URL")
    if webhook_url:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    webhook_url,
                    json={
                        "alert_type": "accuracy_degradation",
                        "level": alert_data["level"],
                        "window": alert_data["window"],
                        "accuracy": f"{alert_data['accuracy']:.1%}",
                        "threshold": f"{alert_data['threshold']:.1%}",
                        "sample_size": alert_data["sample_size"],
                        "timestamp": alert_data["timestamp"].isoformat(),
                    },
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        logger.info(f"Webhook notification sent to {webhook_url}")
                    else:
                        logger.warning(f"Webhook failed: {resp.status}")
        except Exception as e:
            logger.error(f"Failed to send webhook: {e}")

    # Email notification
    email_to = os.getenv("ALERT_EMAIL_TO")
    if email_to:
        try:
            smtp_host = os.getenv("SMTP_HOST", "localhost")
            smtp_port = int(os.getenv("SMTP_PORT", "25"))
            smtp_user = os.getenv("SMTP_USER")
            smtp_pass = os.getenv("SMTP_PASS")
            email_from = os.getenv("ALERT_EMAIL_FROM", "utxoracle@localhost")

            msg = MIMEMultipart()
            msg["From"] = email_from
            msg["To"] = email_to
            msg["Subject"] = (
                f"[UTXOracle] Accuracy Alert ({alert_data['level'].upper()})"
            )

            body = f"""
Accuracy Alert - UTXOracle Whale Detector

Level: {alert_data["level"].upper()}
Window: {alert_data["window"]}
Current Accuracy: {alert_data["accuracy"]:.1%}
Threshold: {alert_data["threshold"]:.1%}
Sample Size: {alert_data["sample_size"]}
Timestamp: {alert_data["timestamp"].isoformat()}

Action Required: Check system logs and correlation tracking for details.
"""
            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(smtp_host, smtp_port) as server:
                if smtp_user and smtp_pass:
                    server.starttls()
                    server.login(smtp_user, smtp_pass)
                server.send_message(msg)
                logger.info(f"Email notification sent to {email_to}")
        except Exception as e:
            logger.error(f"Failed to send email: {e}")


# Example usage / entry point
async def main():
    """Main entry point for standalone execution"""
    monitor = AccuracyMonitor(
        alert_callback=example_alert_callback,
    )

    try:
        await monitor.start()

        # Run indefinitely
        while True:
            await asyncio.sleep(60)
            stats = monitor.get_stats()
            logger.info(f"Monitor stats: {stats}")

    except KeyboardInterrupt:
        logger.info("\n🛑 Shutting down...")
        await monitor.stop()


if __name__ == "__main__":
    asyncio.run(main())
