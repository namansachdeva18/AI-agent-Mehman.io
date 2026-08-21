"""Google Gemini LLM provider.

Wraps the official google-genai SDK. All Gemini-specific code
is isolated in this module — nothing else in the codebase
should import from google.genai directly.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from app.config import settings
from app.errors import AppError, ErrorCode
from app.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    """Gemini API provider using the official google-genai SDK."""

    def __init__(self) -> None:
        self._client = None
        self._model_name = settings.gemini_model

        if settings.gemini_configured:
            try:
                from google import genai

                self._client = genai.Client(api_key=settings.gemini_api_key)
                logger.info(
                    "GeminiProvider initialized with model: %s", self._model_name
                )
            except ImportError:
                logger.warning(
                    "google-genai package not installed. Gemini features unavailable."
                )
            except Exception as e:
                logger.warning("Failed to initialize Gemini client: %s", e)
        else:
            logger.info(
                "GEMINI_API_KEY not configured. LLM features are unavailable."
            )

    def is_configured(self) -> bool:
        """Check whether the Gemini client is ready."""
        return self._client is not None

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        """Generate a text response from Gemini."""
        if not self.is_configured():
            raise AppError(
                code=ErrorCode.CONFIGURATION_ERROR,
                message="Gemini API is not configured. Set GEMINI_API_KEY.",
                status_code=503,
            )

        try:
            from google.genai import types

            config = types.GenerateContentConfig(
                temperature=0.2,
                system_instruction=system_prompt if system_prompt else None,
            )

            response = await asyncio.to_thread(
                self._client.models.generate_content,
                model=self._model_name,
                contents=prompt,
                config=config,
            )
            return response.text or ""

        except AppError:
            raise
        except Exception as e:
            logger.error("Gemini generate() failed: %s", e)
            raise AppError(
                code=ErrorCode.LLM_ERROR,
                message=f"Gemini API call failed: {e}",
                status_code=502,
            ) from e

    async def generate_structured(
        self,
        prompt: str,
        response_schema: dict[str, Any] | None = None,
        system_prompt: str = "",
    ) -> dict[str, Any]:
        """Generate a structured JSON response from Gemini."""
        if not self.is_configured():
            raise AppError(
                code=ErrorCode.CONFIGURATION_ERROR,
                message="Gemini API is not configured. Set GEMINI_API_KEY.",
                status_code=503,
            )

        try:
            from google.genai import types

            schema_prompt = prompt
            if response_schema:
                schema_prompt += (
                    f"\n\nRespond ONLY with a JSON object matching this schema:\n"
                    f"{json.dumps(response_schema, indent=2)}"
                )

            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
                system_instruction=system_prompt if system_prompt else None,
            )

            response = await asyncio.to_thread(
                self._client.models.generate_content,
                model=self._model_name,
                contents=schema_prompt,
                config=config,
            )

            raw_text = response.text or "{}"
            # Clean markdown JSON fences if model enclosed it
            clean_text = raw_text.strip()
            if clean_text.startswith("```"):
                clean_text = re.sub(r"^```(?:json)?\n?", "", clean_text)
                clean_text = re.sub(r"\n?```$", "", clean_text)

            return json.loads(clean_text)

        except json.JSONDecodeError as e:
            logger.error("Failed to parse Gemini structured response: %s", e)
            raise AppError(
                code=ErrorCode.LLM_ERROR,
                message="Gemini returned invalid JSON.",
                status_code=502,
            ) from e
        except AppError:
            raise
        except Exception as e:
            logger.error("Gemini generate_structured() failed: %s", e)
            raise AppError(
                code=ErrorCode.LLM_ERROR,
                message=f"Gemini API call failed: {e}",
                status_code=502,
            ) from e

