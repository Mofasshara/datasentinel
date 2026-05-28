from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Anthropic
    anthropic_api_key: str
    claude_model: str = "claude-sonnet-4-6"
    claude_max_tokens: int = 4096

    # Postgres
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "datasentinel"
    postgres_password: str = "datasentinel"
    postgres_db: str = "datasentinel"

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"

    # Semantic validator
    semantic_batch_size: int = 50
    semantic_max_failures_stored: int = 100
    embedding_model: str = "all-MiniLM-L6-v2"

    # Pipeline agent
    openmetadata_host: str = "http://localhost:8585"
    openmetadata_token: str = ""
    sandbox_timeout_seconds: int = 60
    max_fix_iterations: int = 3

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
