# Configuration management

from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List

class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/file_allocator"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    
    # Storage
    storage_backend: str = "fs://"
    storage_path: str = "./storage"
    
    # S3 (if using s3:// backend)
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"
    s3_bucket: str = "file-allocator"
    
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
    cluster_threshold: float = 0.8
    max_image_size: int = 1024
    video_keyframes: int = 3
    
    # Schema Decision
    schema_sample_size: int = 128
    schema_stability_threshold: float = 0.6
    schema_max_top_level_keys: int = 20
    schema_max_depth: int = 2
    auto_migrate: bool = False
    
    # Security
    api_key: str = ""
    allowed_origins: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    
    # Observability
    metrics_enabled: bool = True
    tracing_enabled: bool = False
    
    class Config:
        env_file = ".env"
        case_sensitive = False

@lru_cache()
def get_settings() -> Settings:
    return Settings()

