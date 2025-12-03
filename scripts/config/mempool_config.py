#!/usr/bin/env python3
"""
Shared Configuration Module for Mempool Whale Detection
Task T010: Centralized configuration management

Provides configuration for all system components with environment variable overrides.
"""

import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class MempoolConfig:
    """
    Main configuration for mempool whale detection system

    All settings can be overridden via environment variables.
    """

    # ==================== Infrastructure ====================
    # Mempool.space WebSocket
    mempool_ws_url: str = field(
        default_factory=lambda: os.getenv(
            "MEMPOOL_WS_URL", "ws://localhost:8999/ws/track-mempool-tx"
        )
    )

    # Mempool.space HTTP API
    mempool_http_url: str = field(
        default_factory=lambda: os.getenv(
            "MEMPOOL_HTTP_URL", "http://localhost:8999/api/v1"
        )
    )

    # electrs HTTP API
    electrs_http_url: str = field(
        default_factory=lambda: os.getenv("ELECTRS_HTTP_URL", "http://localhost:3001")
    )

    # ==================== Database ====================
    database_path: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_PATH", "data/mempool_predictions.db"
        )
    )

    # Data retention (days)
    retention_days: int = field(
        default_factory=lambda: int(os.getenv("RETENTION_DAYS", "90"))
    )

    # ==================== Whale Detection ====================
    # Minimum BTC value to classify as whale
    whale_threshold_btc: float = field(
        default_factory=lambda: float(os.getenv("WHALE_THRESHOLD_BTC", "100.0"))
    )

    # ==================== Urgency Scoring ====================
    # Fee percentiles for urgency calculation
    urgency_update_interval_seconds: int = field(
        default_factory=lambda: int(os.getenv("URGENCY_UPDATE_INTERVAL", "60"))
    )

    # ==================== Memory Management ====================
    # Maximum memory usage (MB)
    max_memory_mb: int = field(
        default_factory=lambda: int(os.getenv("MAX_MEMORY_MB", "500"))
    )

    # Memory warning threshold (MB)
    memory_warning_threshold_mb: int = field(
        default_factory=lambda: int(os.getenv("MEMORY_WARNING_THRESHOLD_MB", "400"))
    )

    # Transaction cache size
    transaction_cache_size: int = field(
        default_factory=lambda: int(os.getenv("TRANSACTION_CACHE_SIZE", "10000"))
    )

    # ==================== WebSocket Server ====================
    # Alert broadcaster settings
    broadcaster_host: str = field(
        default_factory=lambda: os.getenv("BROADCASTER_HOST", "localhost")
    )
    broadcaster_port: int = field(
        default_factory=lambda: int(os.getenv("BROADCASTER_PORT", "8765"))
    )

    # Authentication
    auth_enabled: bool = field(
        default_factory=lambda: os.getenv("AUTH_ENABLED", "true").lower() == "true"
    )
    websocket_secret_key: Optional[str] = field(
        default_factory=lambda: os.getenv("WEBSOCKET_SECRET_KEY")
    )

    # ==================== REST API ====================
    api_host: str = field(default_factory=lambda: os.getenv("API_HOST", "localhost"))
    api_port: int = field(default_factory=lambda: int(os.getenv("API_PORT", "8000")))

    # ==================== Logging ====================
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    log_mode: str = field(
        default_factory=lambda: os.getenv("LOG_MODE", "development")
    )  # development or production
    log_dir: str = field(default_factory=lambda: os.getenv("LOG_DIR", "logs"))

    # ==================== Performance ====================
    # WebSocket reconnection settings
    ws_reconnect_delay_seconds: int = field(
        default_factory=lambda: int(os.getenv("WS_RECONNECT_DELAY", "5"))
    )
    ws_max_reconnect_attempts: int = field(
        default_factory=lambda: int(os.getenv("WS_MAX_RECONNECT_ATTEMPTS", "10"))
    )

    # Rate limiting
    rate_limit_requests_per_minute: int = field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_REQUESTS", "100"))
    )

    # ==================== Monitoring ====================
    # Accuracy monitoring
    accuracy_check_interval_minutes: int = field(
        default_factory=lambda: int(os.getenv("ACCURACY_CHECK_INTERVAL", "60"))
    )
    accuracy_threshold: float = field(
        default_factory=lambda: float(os.getenv("ACCURACY_THRESHOLD", "0.7"))
    )

    # ==================== Feature Flags ====================
    # Enable/disable specific features
    enable_webhooks: bool = field(
        default_factory=lambda: os.getenv("ENABLE_WEBHOOKS", "false").lower() == "true"
    )
    enable_operator_alerts: bool = field(
        default_factory=lambda: os.getenv("ENABLE_OPERATOR_ALERTS", "true").lower()
        == "true"
    )

    def __post_init__(self):
        """Validate configuration after initialization"""
        # Ensure directories exist
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.log_dir).mkdir(parents=True, exist_ok=True)

        # Validate thresholds
        if self.whale_threshold_btc <= 0:
            raise ValueError("whale_threshold_btc must be positive")
        if self.memory_warning_threshold_mb >= self.max_memory_mb:
            raise ValueError(
                "memory_warning_threshold_mb must be less than max_memory_mb"
            )
        if self.accuracy_threshold < 0 or self.accuracy_threshold > 1:
            raise ValueError("accuracy_threshold must be between 0 and 1")

    def to_dict(self) -> dict:
        """Convert configuration to dictionary"""
        return {
            field_name: getattr(self, field_name)
            for field_name in self.__dataclass_fields__
        }

    def __repr__(self) -> str:
        """String representation (hides sensitive data)"""
        config_dict = self.to_dict()
        # Mask sensitive keys
        if config_dict.get("websocket_secret_key"):
            config_dict["websocket_secret_key"] = "***REDACTED***"
        return f"MempoolConfig({config_dict})"


# Singleton instance
_config: Optional[MempoolConfig] = None


def get_config() -> MempoolConfig:
    """
    Get the global configuration instance (singleton)

    Returns:
        MempoolConfig instance
    """
    global _config
    if _config is None:
        _config = MempoolConfig()
    return _config


def reload_config() -> MempoolConfig:
    """
    Reload configuration from environment variables

    Returns:
        New MempoolConfig instance
    """
    global _config
    _config = MempoolConfig()
    return _config


# Example usage and testing
if __name__ == "__main__":
    import json

    # Load configuration
    config = get_config()

    print("✅ Configuration loaded successfully")
    print("\n📊 Configuration:")
    print("=" * 60)

    # Group settings by category
    categories = {
        "Infrastructure": [
            "mempool_ws_url",
            "mempool_http_url",
            "electrs_http_url",
        ],
        "Database": ["database_path", "retention_days"],
        "Whale Detection": ["whale_threshold_btc"],
        "Memory Management": [
            "max_memory_mb",
            "memory_warning_threshold_mb",
            "transaction_cache_size",
        ],
        "WebSocket Server": ["broadcaster_host", "broadcaster_port", "auth_enabled"],
        "REST API": ["api_host", "api_port"],
        "Logging": ["log_level", "log_mode", "log_dir"],
        "Monitoring": ["accuracy_check_interval_minutes", "accuracy_threshold"],
        "Feature Flags": ["enable_webhooks", "enable_operator_alerts"],
    }

    for category, fields in categories.items():
        print(f"\n{category}:")
        for field_name in fields:
            value = getattr(config, field_name)
            print(f"  {field_name}: {value}")

    # Test environment variable override
    print("\n\n🧪 Testing environment variable override:")
    os.environ["WHALE_THRESHOLD_BTC"] = "200.0"
    os.environ["LOG_LEVEL"] = "DEBUG"

    new_config = reload_config()
    print(f"  whale_threshold_btc: {new_config.whale_threshold_btc}")
    print(f"  log_level: {new_config.log_level}")

    # Test serialization
    print("\n📄 JSON export (first 10 fields):")
    config_dict = config.to_dict()
    sample = dict(list(config_dict.items())[:10])
    print(json.dumps(sample, indent=2, default=str))

    print("\n✅ Configuration tests passed")
