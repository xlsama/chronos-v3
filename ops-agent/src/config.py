from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://chronos:chronos@localhost:5432/chronos"
    langgraph_checkpoint_dsn: str = "postgresql://chronos:chronos@localhost:5432/chronos"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # DashScope / Bailian
    dashscope_api_key: str = ""
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    main_model: str = "qwen-plus"
    mini_model: str = "qwen-turbo"
    embedding_model: str = "text-embedding-v3"
    embedding_dimension: int = 1024

    # Upload
    upload_dir: str = "uploads"

    # Security
    encryption_key: str = "dGVzdC1lbmNyeXB0aW9uLWtleS0zMmJ5dGVz"
    jwt_secret: str = "dev-jwt-secret"


@lru_cache
def get_settings() -> Settings:
    return Settings()
