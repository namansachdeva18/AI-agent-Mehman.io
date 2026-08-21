"""LLM provider interface.

A minimal abstraction so the orchestrator depends on a clean interface
rather than directly importing Gemini SDK classes.

There is only ONE provider (Gemini). This abstraction exists to:
1. Keep the orchestrator testable (can mock the provider)
2. Isolate all SDK-specific code in gemini.py
3. Define a clear contract for LLM operations
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """Interface for LLM operations used by the agent orchestrator."""

    @abstractmethod
    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        """Generate a free-form text response.

        Args:
            prompt: The user/context prompt.
            system_prompt: Optional system-level instructions.

        Returns:
            The model's text response.
        """
        ...

    @abstractmethod
    async def generate_structured(
        self,
        prompt: str,
        response_schema: dict[str, Any],
        system_prompt: str = "",
    ) -> dict[str, Any]:
        """Generate a response conforming to a JSON schema.

        Used for extracting structured data (booking info, decisions)
        from natural language.

        Args:
            prompt: The user/context prompt.
            response_schema: JSON schema the response must conform to.
            system_prompt: Optional system-level instructions.

        Returns:
            Parsed dict matching the response schema.
        """
        ...

    @abstractmethod
    def is_configured(self) -> bool:
        """Check whether this provider has valid configuration to make API calls."""
        ...
