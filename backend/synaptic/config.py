from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Synaptic configuration from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Chain
    alchemy_ws_url: str = "wss://eth-mainnet.g.alchemy.com/v2/YOUR_KEY"
    alchemy_http_url: str = "https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY"
    chain_id: int = 1

    # Simulation
    anvil_url: str = "http://127.0.0.1:8545"
    fork_pool_size: int = 3
    fork_block_lag: int = 5

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Etherscan
    etherscan_api_key: str = ""

    # Logging
    log_level: str = "INFO"

    # Protocol configs (Phase 1: AMM only)
    # Format: {"protocol_name": {"address": "0x...", "abi_path": "abis/protocol.json", "tvl": 1000000}}
    monitored_protocols: str = "{}"  # JSON string; parsed at runtime


settings = Settings()
