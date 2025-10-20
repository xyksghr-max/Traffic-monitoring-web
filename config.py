"""Application configuration for the traffic monitoring algorithm service."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    """Centralised runtime configuration loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_prefix="ALGO_",
        env_file=os.getenv("ALGO_ENV_FILE"),
        env_file_encoding="utf-8",
        protected_namespaces=("settings_",),
    )

    server_host: str = Field(default="0.0.0.0", description="Host that the Flask app binds to")
    server_port: int = Field(default=5000, description="Port that the Flask app listens on")
    frame_interval: float = Field(default=1.8, description="Seconds between detection frames")
    alert_pause_seconds: float = Field(default=3.0, description="Pause after high-risk detection")

    backend_base_url: str = Field(
        default="http://localhost:9090/api",
        description="Spring Boot backend base URL for auxiliary requests",
    )

    weights_dir: Path = Field(default=BASE_DIR / "weights", description="Directory containing YOLO weights")
    model_config_path: Path = Field(default=BASE_DIR / "model_config.yaml", description="Model configuration file")

    llm_model: str = Field(default="qwen-vl-plus", description="Default multimodal model identifier")
    llm_timeout: int = Field(default=30, description="Timeout for LLM requests in seconds")
    llm_max_retry: int = Field(default=2, description="Maximum retry count for LLM calls")
    
    # Streaming mode configuration
    enable_kafka_streaming: bool = Field(default=False, description="Enable Kafka streaming for async LLM processing")
    kafka_bootstrap_servers: str = Field(default="localhost:9092", description="Kafka broker addresses")

    allowed_classes: List[str] = Field(
        default_factory=lambda: [
            "person",
            "bicycle",
            "car",
            "motorcycle",
            "bus",
            "truck",
            "traffic_light",
            "stop_sign",
        ],
        description="Object classes to retain from YOLO detections",
    )


settings = Settings()
