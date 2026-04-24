from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM API keys
    groq_api_key: Optional[str] = Field(default=None, alias="GROQ_API_KEY")
    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    openrouter_api_key: Optional[str] = Field(default=None, alias="OPENROUTER_API_KEY")


    # Model choices per role
    # Groq — strict routing/formatting (Orchestrator, Summarizer)
    groq_model: str = Field(default="llama-3.3-70b-versatile", alias="GROQ_MODEL")
    # Gemini 1.5 Flash — large context window (Diagnosis, Eval agents)
    gemini_model: str = Field(default="gemini-1.5-flash", alias="GEMINI_MODEL")
    # OpenRouter — simpler sub-tasks / final fallback
    openrouter_model: str = Field(default="meta-llama/llama-3-8b-instruct:free", alias="OPENROUTER_MODEL")


    # Vector store
    qdrant_url: str = Field(default="http://localhost:6333", alias="QDRANT_URL")
    qdrant_api_key: Optional[str] = Field(default=None, alias="QDRANT_API_KEY")

    # Neo4j knowledge graph
    neo4j_uri: str = Field(default="bolt://localhost:7687", alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", alias="NEO4J_USER")
    neo4j_password: Optional[str] = Field(default=None, alias="NEO4J_PASSWORD")

    # Observability
    langfuse_public_key: Optional[str] = Field(default=None, alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: Optional[str] = Field(default=None, alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="http://localhost:3001", alias="LANGFUSE_HOST")

    # Database
    database_url: str = Field(default="sqlite:///./medcontext.db", alias="DATABASE_URL")
    database_key: Optional[str] = Field(default=None, alias="DATABASE_KEY")

    # App / filesystem
    data_root: str = Field(default="data", alias="DATA_ROOT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    secret_key: str = Field(default="change-me-in-production", alias="SECRET_KEY")
    allowed_origins: list[str] = Field(
        default=["http://localhost:7860", "http://localhost:8000"],
        alias="ALLOWED_ORIGINS",
    )

    # Computed paths
    @computed_field
    @property
    def data_root_path(self) -> Path:
        return Path(self.data_root).resolve()

    @computed_field
    @property
    def patient_dir(self) -> Path:
        p = self.data_root_path / "patients"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @computed_field
    @property
    def seed_dir(self) -> Path:
        return self.data_root_path / "seed"

    @computed_field
    @property
    def cache_dir(self) -> Path:
        c = self.data_root_path / ".cache"
        c.mkdir(parents=True, exist_ok=True)
        return c

    # Provider availability flags
    @computed_field
    @property
    def has_groq(self) -> bool:
        return bool(self.groq_api_key)

    @computed_field
    @property
    def has_gemini(self) -> bool:
        return bool(self.gemini_api_key)

    @computed_field
    @property
    def has_openrouter(self) -> bool:
        return bool(self.openrouter_api_key)

    @computed_field
    @property
    def has_neo4j(self) -> bool:
        return bool(self.neo4j_password)

settings = Settings()
