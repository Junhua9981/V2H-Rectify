"""
Centralised configuration — Pydantic Settings.

Every hardcoded value that used to be scattered across v2 modules now lives here.
All values are overridable via environment variables or a `.env` file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CRAFTSettings(BaseSettings):
    """CRAFT text-detection model parameters."""

    languages: list[str] = Field(default=["ch_tra"])
    canvas_size: int = Field(default=2560)
    text_threshold: float = 0.7
    link_threshold: float = 0.4
    low_text: float = 0.4
    mag_ratio: float = 1.0
    batch_size: int = Field(default=8, ge=1, le=64)
    batch_timeout: float = Field(default=0.1, ge=0.01)


class VLMSettings(BaseSettings):
    """VLM / LLM backend configuration."""

    backend: Literal["vllm", "gemini", "openai"] = "vllm"

    # vLLM
    vllm_base_url: str = "http://localhost:8000/v1"
    vllm_api_key: str = "EMPTY"
    vllm_model_name: str = "Qwen/Qwen3-VL-2B-Instruct"

    # Gemini
    gemini_api_key: str = ""
    gemini_model_name: str = "gemini-2.0-flash"

    # OpenAI
    openai_api_key: str = ""
    openai_model_name: str = "gpt-4o"


class OCRPipelineSettings(BaseSettings):
    """OCR pipeline feature flags and parameters."""

    auto_rotate: bool = True
    remove_print: bool = True
    auto_split: bool = True
    max_workers: int = Field(default=4, ge=1, le=32)
    timeout: int = Field(default=120, ge=10)

    # Rotation corrector
    rotation_min_centroids: int = 10
    rotation_min_clusters: int = 3
    rotation_max_angle: float = 45.0

    # Print text remover
    print_angle_threshold: float = 3.0
    print_row_ratio_threshold: float = 0.8

    # Image splitter
    split_aspect_ratio: float = 2.0

    # Debug
    debug_enabled: bool = False
    debug_dir: Path = Path("./debug/ocr_pipeline")


class ServerSettings(BaseSettings):
    """Web server settings."""

    host: str = "0.0.0.0"
    port: int = 8080
    workers: int = 1
    upload_dir: Path = Path("./uploads")
    max_upload_size_mb: int = 20


class Settings(BaseSettings):
    """Root settings — aggregates all sub-settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # GPU
    cuda_device: str = "cuda:7"

    # Sub-configs (populated via env prefix or defaults)
    craft: CRAFTSettings = Field(default_factory=CRAFTSettings)
    vlm: VLMSettings = Field(default_factory=VLMSettings)
    pipeline: OCRPipelineSettings = Field(default_factory=OCRPipelineSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)

    # Logging
    log_level: str = "INFO"
    log_format: Literal["simple", "default", "detailed"] = "default"
    log_file: str = ""

    # Redis (not used yet, but reserved for future WebSocket progress updates)
    # redis_url: str = "redis://localhost:6379/0"


# Singleton-ish convenience — import this from anywhere.
_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the global Settings instance (created on first call)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
