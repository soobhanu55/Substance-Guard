from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- neo4j ---
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "substanceguard"
    neo4j_database: str = "neo4j"

    # --- qdrant ---
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""  # required for Qdrant Cloud; empty for local/docker-compose Qdrant
    qdrant_collection_clauses: str = "reg_clauses"
    qdrant_collection_fixed: str = "reg_fixed"

    # --- llm ---
    llm_provider: Literal["gemini", "anthropic"] = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.1-flash-lite"
    gemini_embedding_model: str = "gemini-embedding-001"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    # --- pipeline / review ---
    checkpoint_db_path: str = "data/checkpoints.sqlite"
    review_queue_path: str = "data/review_queue.json"
    borderline_band_pct: float = 10.0  # +/- relative % around a threshold => NEEDS_REVIEW

    # --- app ---
    log_level: str = "INFO"
    app_env: Literal["dev", "test", "prod"] = "dev"
    max_upload_mb: int = 15


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
