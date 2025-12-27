"""
RBN API Fetcher for ResearchBitcoin.net integration (spec-035).
Task T010: Core RBN data fetching logic with caching.
"""

import json
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx
import pandas as pd

from api.models.validation_models import (
    RBN_METRICS,
    QuotaExceededError,
    QuotaInfo,
    RBNConfig,
    RBNMetricInfo,
    RBNMetricResponse,
    RBNTier,
)

logger = logging.getLogger(__name__)


class RBNFetcher:
    """
    Fetches metric data from ResearchBitcoin.net API.

    Features:
    - 24-hour Parquet cache to minimize API calls
    - Local quota tracking to prevent overages
    - Automatic token injection from config
    """

    def __init__(
        self,
        config: Optional[RBNConfig] = None,
        cache_dir: Optional[Path] = None,
    ):
        """
        Initialize RBN fetcher.

        Args:
            config: RBN API configuration. If None, loads from environment.
            cache_dir: Cache directory path. Defaults to cache/rbn/.
        """
        self.config = config or self._load_config_from_env()
        self.cache_dir = cache_dir or Path("cache/rbn")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Initialize httpx client with timeout
        self._client: Optional[httpx.AsyncClient] = None

        # Quota tracking file
        self._quota_file = self.cache_dir / "quota_tracking.json"

    def _load_config_from_env(self) -> RBNConfig:
        """Load configuration from environment variables."""
        from pydantic import SecretStr

        token = os.getenv("RBN_API_TOKEN", "")
        if not token:
            raise ValueError("RBN_API_TOKEN environment variable not set")

        return RBNConfig(
            token=SecretStr(token),
            tier=RBNTier(int(os.getenv("RBN_TIER", "0"))),
            cache_ttl_hours=int(os.getenv("RBN_CACHE_TTL_HOURS", "24")),
            timeout_seconds=float(os.getenv("RBN_TIMEOUT_SECONDS", "30")),
        )

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create httpx client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.timeout_seconds)
            )
        return self._client

    async def close(self) -> None:
        """Close httpx client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _get_cache_path(self, metric_id: str) -> Path:
        """Get cache file path for a metric."""
        return self.cache_dir / f"{metric_id}.parquet"

    def _is_cache_valid(self, cache_path: Path) -> bool:
        """Check if cache file exists and is within TTL."""
        if not cache_path.exists():
            return False

        # Check file modification time
        mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
        ttl = timedelta(hours=self.config.cache_ttl_hours)
        return datetime.now() - mtime < ttl

    async def fetch_metric(
        self,
        metric_id: str,
        start_date: date,
        end_date: Optional[date] = None,
        force_refresh: bool = False,
    ) -> RBNMetricResponse:
        """
        Fetch metric data from RBN API.

        Args:
            metric_id: Metric identifier (e.g., 'mvrv_z')
            start_date: Start date for data range
            end_date: End date (defaults to today)
            force_refresh: Skip cache check

        Returns:
            RBNMetricResponse with data points

        Raises:
            ValueError: If metric_id not found
            QuotaExceededError: If quota exceeded
            httpx.HTTPError: On network errors
        """
        if metric_id not in RBN_METRICS:
            raise ValueError(f"Unknown metric: {metric_id}")

        metric_info = RBN_METRICS[metric_id]
        end_date = end_date or date.today()

        # Check cache first
        cache_path = self._get_cache_path(metric_id)
        if not force_refresh and self._is_cache_valid(cache_path):
            logger.info(f"Cache hit for {metric_id}")
            return self._load_from_cache(cache_path, metric_id, start_date, end_date)

        # Check quota before making request
        await self._check_quota()

        # Build request URL
        url = self._build_url(metric_info, start_date, end_date)

        # Make request
        logger.info(f"Fetching {metric_id} from RBN API")
        client = await self._get_client()
        response = await client.get(url)

        # Handle errors
        if response.status_code == 401:
            raise ValueError("Invalid RBN API token")
        if response.status_code == 429:
            quota_info = await self.get_quota_info()
            raise QuotaExceededError(quota_info)
        response.raise_for_status()

        # Parse response
        data = response.json()
        result = RBNMetricResponse.from_api_response(data, metric_id)

        # Save to cache
        self._save_to_cache(result)

        # Update quota tracking
        await self._increment_quota()

        return result

    def _build_url(
        self,
        metric_info: RBNMetricInfo,
        start_date: date,
        end_date: date,
    ) -> str:
        """Build API request URL."""
        base = self.config.base_url
        endpoint = metric_info.endpoint
        token = self.config.token.get_secret_value()

        return (
            f"{base}{endpoint}"
            f"?token={token}"
            f"&start_date={start_date.isoformat()}"
            f"&end_date={end_date.isoformat()}"
            f"&output_format=json"
        )

    def _save_to_cache(self, response: RBNMetricResponse) -> None:
        """Save response data to Parquet cache."""
        if not response.data:
            return

        # Convert to DataFrame
        df = pd.DataFrame(
            [{"date": dp.date, "value": dp.value} for dp in response.data]
        )

        cache_path = self._get_cache_path(response.metric_id)
        df.to_parquet(cache_path, index=False)
        logger.debug(f"Saved {len(df)} records to cache: {cache_path}")

    def _load_from_cache(
        self,
        cache_path: Path,
        metric_id: str,
        start_date: date,
        end_date: date,
    ) -> RBNMetricResponse:
        """Load metric data from Parquet cache."""
        df = pd.read_parquet(cache_path)

        # Filter by date range
        df["date"] = pd.to_datetime(df["date"]).dt.date
        mask = (df["date"] >= start_date) & (df["date"] <= end_date)
        df = df[mask]

        from api.models.validation_models import RBNDataPoint

        data_points = [
            RBNDataPoint(date=row["date"], value=row["value"])
            for _, row in df.iterrows()
        ]

        return RBNMetricResponse(
            status="success",
            message="Data loaded from cache",
            metric_id=metric_id,
            data=data_points,
            output_format="json",
            timestamp=datetime.now(),
            cached=True,
        )

    async def _check_quota(self) -> None:
        """Check if quota allows another request."""
        quota = self._load_quota_tracking()
        if quota["used_this_week"] >= quota["weekly_limit"]:
            raise QuotaExceededError(
                QuotaInfo(
                    tier=RBNTier(quota["tier"]),
                    weekly_limit=quota["weekly_limit"],
                    used_this_week=quota["used_this_week"],
                    remaining=0,
                    reset_at=datetime.fromisoformat(quota["reset_at"]),
                )
            )

    async def _increment_quota(self) -> None:
        """Increment local quota counter."""
        quota = self._load_quota_tracking()
        quota["used_this_week"] += 1
        self._save_quota_tracking(quota)

    def _load_quota_tracking(self) -> dict:
        """Load quota tracking from JSON file."""
        if not self._quota_file.exists():
            # Initialize quota tracking
            return self._init_quota_tracking()

        with open(self._quota_file) as f:
            quota = json.load(f)

        # Check if reset is due
        reset_at = datetime.fromisoformat(quota["reset_at"])
        if datetime.now() >= reset_at:
            return self._init_quota_tracking()

        return quota

    def _init_quota_tracking(self) -> dict:
        """Initialize fresh quota tracking."""
        # Weekly limits by tier
        limits = {0: 100, 1: 300, 2: 10000}

        # Reset at midnight next Sunday
        now = datetime.now()
        days_until_sunday = (6 - now.weekday()) % 7
        if days_until_sunday == 0:
            days_until_sunday = 7
        reset_at = (now + timedelta(days=days_until_sunday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        quota = {
            "tier": self.config.tier.value,
            "weekly_limit": limits[self.config.tier.value],
            "used_this_week": 0,
            "reset_at": reset_at.isoformat(),
        }
        self._save_quota_tracking(quota)
        return quota

    def _save_quota_tracking(self, quota: dict) -> None:
        """Save quota tracking to JSON file."""
        with open(self._quota_file, "w") as f:
            json.dump(quota, f, indent=2)

    async def get_quota_info(self) -> QuotaInfo:
        """Get current quota status."""
        quota = self._load_quota_tracking()
        return QuotaInfo(
            tier=RBNTier(quota["tier"]),
            weekly_limit=quota["weekly_limit"],
            used_this_week=quota["used_this_week"],
            remaining=quota["weekly_limit"] - quota["used_this_week"],
            reset_at=datetime.fromisoformat(quota["reset_at"]),
        )

    def clear_cache(self, metric_id: Optional[str] = None) -> int:
        """
        Clear cached data.

        Args:
            metric_id: Clear only this metric. If None, clears all.

        Returns:
            Number of cache files cleared.
        """
        if metric_id:
            cache_path = self._get_cache_path(metric_id)
            if cache_path.exists():
                cache_path.unlink()
                logger.info(f"Cleared cache for {metric_id}")
                return 1
            return 0

        # Clear all parquet files
        count = 0
        for f in self.cache_dir.glob("*.parquet"):
            f.unlink()
            count += 1
        logger.info(f"Cleared {count} cache files")
        return count
