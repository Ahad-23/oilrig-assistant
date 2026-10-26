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
    GROQ_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    OPEN_ROUTER_API_KEY: Optional[str] = None

    # Task-Specific OpenRouter Free Models
    PRIMARY_MODEL: str = "openrouter/nvidia/nemotron-3.5-lightning:free"
    FALLBACK_MODEL: str = "openrouter/openrouter/free"
    MODEL_TOOL_PLANNER: str = "openrouter/nvidia/nemotron-3.5-lightning:free"
    MODEL_REASONER: str = "openrouter/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
    MODEL_SYNTHESIZER: str = "openrouter/minimax/minimax-m3.1-flash:free"
    MODEL_SAFETY_NET: str = "openrouter/openrouter/free"

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
