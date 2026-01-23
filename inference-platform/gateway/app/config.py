"""Configuration management for the gateway."""
import os
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # API Keys
    gateway_api_key: str = os.getenv("GATEWAY_API_KEY", "")
    backend_api_key: str = os.getenv("BACKEND_API_KEY", "")
    
    # Backend URLs
    chat_backends: List[str] = []
    text2sql_backend: str = ""
    embed_backend: str = ""
    rerank_backend: str = ""
    
    # Rate Limiting
    max_rps_per_ip: float = 50.0
    rps_window_secs: float = 1.0
    rps_burst: int = 100
    
    # Concurrency Control
    max_inflight_per_ip: int = 120
    queue_timeout_secs: float = 2.0
    
    # Request Timeouts
    max_request_secs: float = 5400.0  # 90 minutes
    stream_idle_timeout_secs: float = 180.0  # 3 minutes
    
    # Quota Management
    org_daily_token_limit: int = 10_000_000
    org_daily_request_limit: int = 100_000
    org_monthly_token_limit: int = 300_000_000
    
    # Caching
    cache_ttl_secs: int = 60
    cache_max_size: int = 10000
    
    # Circuit Breaker
    circuit_failure_threshold: int = 5
    circuit_recovery_timeout: int = 30
    
    # Health Check
    health_check_interval_secs: int = 10
    health_check_timeout_secs: float = 2.0
    
    # Logging
    log_level: str = "INFO"
    enable_pii_redaction: bool = True
    
    # Gateway
    gateway_workers: int = 4
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Parse backend URLs from environment
        chat_backends_str = os.getenv("CHAT_BACKENDS", "")
        if chat_backends_str:
            self.chat_backends = [b.strip() for b in chat_backends_str.split(",") if b.strip()]
        
        self.text2sql_backend = os.getenv("TEXT2SQL_BACKEND", "").strip()
        self.embed_backend = os.getenv("EMBED_BACKEND", "").strip()
        self.rerank_backend = os.getenv("RERANK_BACKEND", "").strip()
        
        # Override from env if present
        self.max_rps_per_ip = float(os.getenv("MAX_RPS_PER_IP", "50"))
        self.rps_window_secs = float(os.getenv("RPS_WINDOW_SECS", "1"))
        self.rps_burst = int(os.getenv("RPS_BURST", "100"))
        self.max_inflight_per_ip = int(os.getenv("MAX_INFLIGHT_PER_IP", "120"))
        self.queue_timeout_secs = float(os.getenv("QUEUE_TIMEOUT_SECS", "2"))
        self.max_request_secs = float(os.getenv("MAX_REQUEST_SECS", "5400"))
        self.stream_idle_timeout_secs = float(os.getenv("STREAM_IDLE_TIMEOUT_SECS", "180"))
        self.gateway_workers = int(os.getenv("GATEWAY_WORKERS", "4"))
        
    def validate(self) -> None:
        """Validate configuration."""
        if not self.gateway_api_key or not self.backend_api_key:
            raise ValueError("GATEWAY_API_KEY and BACKEND_API_KEY must be set")
        
        if not self.chat_backends:
            raise ValueError("CHAT_BACKENDS must be set")
        
        if not self.text2sql_backend:
            raise ValueError("TEXT2SQL_BACKEND must be set")
        
        if not self.embed_backend:
            raise ValueError("EMBED_BACKEND must be set")
        
        if not self.rerank_backend:
            raise ValueError("RERANK_BACKEND must be set")


# Global settings instance
settings = Settings()
