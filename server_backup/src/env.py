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
    main_model: str = "kimi-k2.5"
    mini_model: str = "qwen3.5-flash"
    embedding_model: str = "text-embedding-v4"
    embedding_dimension: int = 1024
    rerank_model: str = "qwen3-rerank"
    rerank_base_url: str = "https://dashscope.aliyuncs.com/compatible-api/v1"
    vision_model: str = "qwen-vl-max"
    stt_model: str = "qwen3-asr-flash-realtime"
    dashscope_ws_url: str = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"

    # Agent

    agent_recursion_limit: int = 200
    tool_call_max_retries: int = 2  # LLM 未调用工具时的最大重试次数
    command_timeout: int = 10  # 命令执行超时（秒），适用于 bash/SSH/服务查询
    max_compact_recent_chars: int = 100000  # compact 输入中最近消息的最大字符数
    proactive_compact_chars: int = 200000  # 主动 compact 触发阈值（消息总字符数）

    # Cron
    skill_evolution_interval: int = 8  # skill 自进化间隔（小时）

    # Data directories
    data_dir: str = "data"
    seeds_dir: str = "seeds"

    # Security — override these in production via environment variables
    encryption_key: str = "dGVzdC1lbmNyeXB0aW9uLWtleS0zMmJ5dGVz"
    jwt_secret: str = "024HX4wfCMjAQMsm9G3LVIhCFERo5G0-mR5s2KxBOqE"

    def validate_production_secrets(self) -> list[str]:
        """Return warnings if default secrets are still in use."""
        warnings = []
        if self.encryption_key == "dGVzdC1lbmNyeXB0aW9uLWtleS0zMmJ5dGVz":
            warnings.append(
                "ENCRYPTION_KEY is using the default dev value — set a unique key in production"
            )
        if self.jwt_secret == "024HX4wfCMjAQMsm9G3LVIhCFERo5G0-mR5s2KxBOqE":
            warnings.append(
                "JWT_SECRET is using the default dev value — set a unique secret in production"
            )
        return warnings


@lru_cache
def get_settings() -> Settings:
    return Settings()
