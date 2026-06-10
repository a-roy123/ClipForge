from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    database_url: str
    redis_url: str
    secret_key: str
    refresh_secret_key: str
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_region: str = "us-east-1"
    s3_bucket_name: str
    celery_broker_url: str
    celery_result_backend: str
    debug: bool = False
    allowed_origins: str = "http://localhost"
    max_upload_size_bytes: int = 2147483648
    max_highlights: int = 5
    default_highlights: int = 3
    default_clip_duration_seconds: int = 30
    min_score_threshold: float = 0.3
    cnn_weight: float = 0.2
    rms_weight: float = 0.4
    motion_weight: float = 0.4

    # Pydantic V2: use SettingsConfigDict, not nested class Config
    # extra="ignore" prevents validation errors from unexpected env vars
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

@lru_cache()
def get_settings() -> Settings:
    return Settings()