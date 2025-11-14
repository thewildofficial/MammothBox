# Configuration management

from pydantic_settings import BaseSettings  # type: ignore
from functools import lru_cache
from typing import List, Optional


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/file_allocator"
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # Storage
    storage_backend: str = "fs://"
    storage_path: str = "./storage"

    # Application
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = False
    log_level: str = "INFO"

    # Workers
    worker_threads: int = 4
    queue_backend: str = "inproc"  # inproc or redis
    redis_url: str = "redis://localhost:6379/0"

    # Media Processing
    embedding_model: str = "openai/clip-vit-base-patch32"
    embedding_dim: int = 512
    cluster_threshold: float = 0.72  # Default threshold per spec
    max_image_size: int = 1024
    video_keyframes: int = 3

    # Document Processing
    text_embedding_model: str = "sentence-transformers/all-mpnet-base-v2"
    doc_chunk_size: int = 512
    doc_chunk_overlap: int = 50

    # VLM Configuration (Gemini)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"  # or gemini-1.5-flash
    vlm_enabled: bool = True
    vlm_timeout: int = 5  # seconds
    vlm_fallback_to_clip: bool = True  # Use CLIP if VLM fails

    # Schema Decision
    schema_sample_size: int = 128
    schema_stability_threshold: float = 0.6
    schema_max_top_level_keys: int = 20
    schema_max_depth: int = 2
    auto_migrate: bool = False

    # Search Configuration
    search_default_limit: int = 10
    search_max_limit: int = 100
    search_default_threshold: float = 0.5
    search_timeout_seconds: int = 30

    # Security
    api_key: str = ""
    allowed_origins: List[str] = [
        "http://localhost:3000", "http://localhost:8000"]
    # Optional root directory for folder ingestion (None = no restriction)
    ingest_allowed_root: Optional[str] = None

    # Observability
    metrics_enabled: bool = True
    tracing_enabled: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
