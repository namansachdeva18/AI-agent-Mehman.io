"""Application configuration using Pydantic Settings.

Loads environment variables with sensible defaults.
The application must start even if GEMINI_API_KEY is not set —
only Gemini-dependent features will be unavailable.
"""

from __future__ import annotations

from typing import Any, Union
import json
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator


class Settings(BaseSettings):
    """Central configuration for the Mehman.io backend."""

    # --- Gemini LLM Configuration ---
    gemini_api_key: str = Field(
        default="",
        description="Google Gemini API key. Leave empty to run without LLM features.",
    )
    gemini_model: str = Field(
        default="gemini-2.5-flash",
        description="Gemini model name for inference.",
    )

    # --- Database ---
    database_url: str = Field(
        default="sqlite:///data/mehman.db",
        description="SQLite database path.",
    )

    # --- Environment & Security ---
    environment: str = Field(
        default="development",
        description="Application environment ('development', 'staging', 'production').",
    )
    allowed_origins: Union[list[str], str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        description="List of allowed CORS origins.",
    )

    @property
    def cors_origins(self) -> list[str]:
        """Normalize allowed origins into a clean list of strings."""
        val = self.allowed_origins
        if isinstance(val, list):
            return val
        if isinstance(val, str):
            val = val.strip()
            if val.startswith("[") and val.endswith("]"):
                try:
                    return json.loads(val)
                except Exception:
                    pass
            return [orig.strip() for orig in val.split(",") if orig.strip()]
        return [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]

    # --- Application ---
    app_name: str = "Mehman.io AI Hotel Booking Agent"
    debug: bool = False

    @property
    def gemini_configured(self) -> bool:
        """Check whether the Gemini API key is actually provided."""
        return bool(self.gemini_api_key)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# Singleton instance — import this throughout the app
settings = Settings()
