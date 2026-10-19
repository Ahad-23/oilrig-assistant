from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # PostgreSQL Configuration (Docker container runs on port 5433)
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "asset_copilot"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5433

    # Computed URLs
    @property
    def async_database_url(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def sync_database_url(self) -> str:
        return f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # LLM & API Keys
    GEMINI_API_KEY: Optional[str] = None
    OPEN_ROUTER_API_KEY: Optional[str] = None
    PRIMARY_MODEL: str = "openrouter/google/gemma-4-26b-a4b-it"
    FALLBACK_MODEL: str = "openrouter/google/gemma-4-31b-it"
    MODEL_TEMPERATURE: float = 0.0
    MODEL_MAX_TOKENS: int = 4096

    # Langfuse Observability Configuration
    LANGFUSE_PUBLIC_KEY: Optional[str] = None
    LANGFUSE_SECRET_KEY: Optional[str] = None
    LANGFUSE_BASE_URL: str = "https://cloud.langfuse.com"
    LANGFUSE_ENVIRONMENT: str = "development"
    LANGFUSE_ENABLED: bool = True

    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATASET_DIR: Path = (
        Path(__file__).resolve().parent.parent / "test-data" / "dataset"
        if (Path(__file__).resolve().parent.parent / "test-data" / "dataset").exists()
        else Path(__file__).resolve().parent.parent / "dataset-problem_statement" / "sample-data"
    )

settings = Settings()
