#!/usr/bin/env python3
"""
Whale Urgency Scorer - Orchestrator Module
Task: T021 - Orchestrates urgency scoring with fee market data

Coordinates UrgencyMetrics updates and provides urgency scoring interface
for whale transactions based on current mempool fee conditions.
"""

import asyncio
import aiohttp
import logging
from typing import Optional

from scripts.models.urgency_metrics import UrgencyMetrics, CongestionLevel

logger = logging.getLogger(__name__)


class WhaleUrgencyScorer:
    """
    Orchestrates urgency scoring for whale transactions

    Features:
    - Fetches fee estimates from mempool.space API
    - Updates UrgencyMetrics periodically
    - Provides urgency score calculation interface
    - Tracks congestion levels
    """

    def __init__(
        self,
        mempool_api_url: str = "http://localhost:8999",
        update_interval_seconds: int = 60,
    ):
        """
        Initialize urgency scorer

        Args:
            mempool_api_url: Base URL for mempool.space API
            update_interval_seconds: How often to refresh fee estimates
        """
        self.mempool_api_url = mempool_api_url.rstrip("/")
        self.update_interval = update_interval_seconds
        self.current_metrics: Optional[UrgencyMetrics] = None
        self.running = False
        self._update_task: Optional[asyncio.Task] = None

        logger.info(
            f"WhaleUrgencyScorer initialized: API={mempool_api_url}, "
            f"update_interval={update_interval_seconds}s"
        )

    async def start(self):
        """Start periodic metrics updates"""
        if self.running:
            logger.warning("Urgency scorer already running")
            return

        self.running = True
        self._update_task = asyncio.create_task(self._update_loop())
        logger.info("Urgency scorer started")

    async def stop(self):
        """Stop periodic metrics updates"""
        self.running = False
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
        logger.info("Urgency scorer stopped")

    async def _update_loop(self):
        """Periodically update fee metrics"""
        while self.running:
            try:
                await self.update_metrics()
                await asyncio.sleep(self.update_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error updating urgency metrics: {e}", exc_info=True)
                await asyncio.sleep(self.update_interval)

    async def update_metrics(self) -> Optional[UrgencyMetrics]:
        """
        Fetch current fee estimates and update metrics

        Returns:
            Updated UrgencyMetrics or None if fetch failed
        """
        try:
            async with aiohttp.ClientSession() as session:
                # Fetch recommended fees from public mempool.space
                # Note: Using public API for fee estimates only (privacy-neutral, public data)
                # Self-hosted mempool doesn't have /fees/recommended endpoint
                fees_url = "https://mempool.space/api/v1/fees/recommended"
                async with session.get(
                    fees_url, timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status != 200:
                        logger.error(f"Fee API returned status {response.status}")
                        return None

                    fees_data = await response.json()

                # Fetch mempool info
                mempool_url = f"{self.mempool_api_url}/api/v1/mempool"
                async with session.get(
                    mempool_url, timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status != 200:
                        logger.warning(
                            f"Mempool API returned status {response.status}, using defaults"
                        )
                        mempool_size_mb = 50.0  # Default
                    else:
                        mempool_data = await response.json()
                        mempool_size_mb = (
                            mempool_data.get("vsize", 50_000_000) / 1_000_000
                        )  # vBytes to MB

                # Fetch current block height
                tip_url = f"{self.mempool_api_url}/api/blocks/tip/height"
                async with session.get(
                    tip_url, timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status != 200:
                        logger.warning(
                            f"Tip API returned status {response.status}, using default"
                        )
                        current_block_height = 850000  # Fallback
                    else:
                        current_block_height = int(await response.text())

            # Build fee percentiles from recommended fees
            # mempool.space provides: fastestFee, halfHourFee, hourFee, economyFee, minimumFee
            fastest = float(fees_data.get("fastestFee", 50))
            half_hour = float(fees_data.get("halfHourFee", 30))
            hour = float(fees_data.get("hourFee", 20))
            economy = float(fees_data.get("economyFee", 10))
            minimum = float(fees_data.get("minimumFee", 1))

            # Map to percentiles (approximation)
            fee_percentiles = {
                "p10": minimum,
                "p25": economy,
                "p50": hour,
                "p75": half_hour,
                "p90": fastest,
            }

            # Estimate blocks to confirmation based on fee tiers
            estimated_blocks = {
                "low_fee": 6,  # Economy fee (~1 hour)
                "medium_fee": 3,  # Half hour fee
                "high_fee": 1,  # Fastest fee
            }

            # Determine congestion level from mempool size
            if mempool_size_mb < 10:
                congestion = CongestionLevel.LOW
            elif mempool_size_mb < 50:
                congestion = CongestionLevel.MEDIUM
            elif mempool_size_mb < 100:
                congestion = CongestionLevel.HIGH
            else:
                congestion = CongestionLevel.EXTREME

            # Create updated metrics
            self.current_metrics = UrgencyMetrics(
                current_block_height=current_block_height,
                fee_percentiles=fee_percentiles,
                estimated_blocks_to_confirmation=estimated_blocks,
                mempool_size_mb=mempool_size_mb,
                congestion_level=congestion,
            )

            logger.info(
                f"Updated urgency metrics: block={current_block_height}, "
                f"mempool_size={mempool_size_mb:.1f}MB, congestion={congestion}, "
                f"fees=[{minimum}-{fastest}]"
            )

            return self.current_metrics

        except asyncio.TimeoutError:
            logger.error("Timeout fetching fee estimates from mempool.space API")
            return None
        except Exception as e:
            logger.error(f"Failed to update urgency metrics: {e}", exc_info=True)
            return None

    def calculate_urgency(self, transaction_fee_rate: float) -> float:
        """
        Calculate urgency score for a transaction

        Args:
            transaction_fee_rate: Fee rate in sat/vB

        Returns:
            Urgency score 0.0-1.0

        Raises:
            RuntimeError: If metrics not initialized
        """
        if self.current_metrics is None:
            raise RuntimeError(
                "Urgency metrics not initialized. Call update_metrics() first."
            )

        return self.current_metrics.calculate_urgency_score(transaction_fee_rate)

    def predict_confirmation_block(self, transaction_fee_rate: float) -> int:
        """
        Predict confirmation block for a transaction

        Args:
            transaction_fee_rate: Fee rate in sat/vB

        Returns:
            Predicted block height

        Raises:
            RuntimeError: If metrics not initialized
        """
        if self.current_metrics is None:
            raise RuntimeError(
                "Urgency metrics not initialized. Call update_metrics() first."
            )

        return self.current_metrics.predict_confirmation_block(transaction_fee_rate)

    def get_current_metrics(self) -> Optional[UrgencyMetrics]:
        """Get current urgency metrics snapshot"""
        return self.current_metrics

    @property
    def is_running(self) -> bool:
        """Check if scorer is running"""
        return self.running

    @property
    def congestion_level(self) -> Optional[CongestionLevel]:
        """Get current congestion level"""
        return self.current_metrics.congestion_level if self.current_metrics else None


# Example usage and testing
if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    async def main():
        scorer = WhaleUrgencyScorer()

        # Fetch metrics once
        metrics = await scorer.update_metrics()
        if metrics is None:
            logger.error("Failed to fetch initial metrics")
            return 1

        print("\n✅ Urgency Metrics Fetched Successfully")
        print(f"   Block Height: {metrics.current_block_height}")
        print(f"   Mempool Size: {metrics.mempool_size_mb:.1f} MB")
        print(f"   Congestion: {metrics.congestion_level}")
        print(f"   Fee Percentiles: {metrics.fee_percentiles}")

        # Test urgency scoring
        print("\n📊 Testing Urgency Scoring:")
        test_fees = [1, 5, 15, 30, 60, 100]
        for fee in test_fees:
            urgency = scorer.calculate_urgency(fee)
            predicted_block = scorer.predict_confirmation_block(fee)
            blocks_ahead = predicted_block - metrics.current_block_height
            print(
                f"   Fee {fee:3d} sat/vB → Urgency: {urgency:.2f}, "
                f"Confirm in ~{blocks_ahead} blocks (height {predicted_block})"
            )

        return 0

    sys.exit(asyncio.run(main()))
