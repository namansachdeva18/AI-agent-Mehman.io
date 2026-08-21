"""Deterministic Tool Executor and Allowlist Registry.

Responsibilities:
- Maintain strict allowlist of deterministic hotel tools
- Validate model-generated arguments against Pydantic input contracts
- Execute tools with execution duration measurement and error trapping
- Prevent execution of arbitrary code, unknown tools, or invalid arguments
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from pydantic import ValidationError

from app.agent.schemas import ToolExecutionEvent, ToolResult
from app.database.connection import Database
from app.errors import AppError, ErrorCode
from app.tools.availability import check_availability
from app.tools.booking_hold import create_booking_hold
from app.tools.contracts import (
    CalculatePriceInput,
    CheckAvailabilityInput,
    CreateBookingHoldInput,
    GetRoomDetailsInput,
    SearchPropertiesInput,
)
from app.tools.pricing import calculate_price
from app.tools.room_details import get_room_details
from app.tools.search import search_properties

logger = logging.getLogger(__name__)

# Strict tool allowlist and argument schema mapping
TOOL_REGISTRY: dict[str, tuple[Callable[..., Any], type]] = {
    "search_properties": (search_properties, SearchPropertiesInput),
    "check_availability": (check_availability, CheckAvailabilityInput),
    "get_room_details": (get_room_details, GetRoomDetailsInput),
    "calculate_price": (calculate_price, CalculatePriceInput),
    "create_booking_hold": (create_booking_hold, CreateBookingHoldInput),
}


class ToolExecutor:
    """Central executor for invoking deterministic hotel tools with safety validation."""

    def __init__(self, db: Database | None = None) -> None:
        self._db = db

    def is_registered(self, tool_name: str) -> bool:
        """Check if tool name is registered in allowlist."""
        return tool_name in TOOL_REGISTRY

    def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        db: Database | None = None,
    ) -> tuple[ToolResult, ToolExecutionEvent]:
        """Validate and execute a registered tool safely."""
        target_db = db or self._db
        start_time = time.perf_counter()

        # 1. Allowlist validation
        if not self.is_registered(tool_name):
            duration_ms = (time.perf_counter() - start_time) * 1000
            err_msg = f"Unknown or disallowed tool: '{tool_name}'. Allowed: {list(TOOL_REGISTRY.keys())}"
            logger.warning(err_msg)
            return (
                ToolResult(tool_name=tool_name, success=False, error=err_msg),
                ToolExecutionEvent(
                    event_type="tool_failed",
                    tool_name=tool_name,
                    duration_ms=duration_ms,
                    success=False,
                    error_code="TOOL_NOT_FOUND",
                    summary=f"Rejected unknown tool '{tool_name}'",
                ),
            )

        tool_func, input_schema = TOOL_REGISTRY[tool_name]

        # 2. Argument validation via Pydantic schema
        try:
            validated_args = input_schema.model_validate(arguments)
        except ValidationError as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            err_msg = f"Invalid arguments for {tool_name}: {e.errors()}"
            logger.warning(err_msg)
            return (
                ToolResult(tool_name=tool_name, success=False, error=err_msg),
                ToolExecutionEvent(
                    event_type="tool_failed",
                    tool_name=tool_name,
                    duration_ms=duration_ms,
                    success=False,
                    error_code="INVALID_ARGUMENTS",
                    summary=f"Argument validation failed for {tool_name}",
                ),
            )

        # 3. Deterministic tool execution
        try:
            output = tool_func(validated_args, db=target_db)
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Convert Pydantic response to dict
            output_dict = output.model_dump() if hasattr(output, "model_dump") else dict(output)

            return (
                ToolResult(tool_name=tool_name, success=True, data=output_dict),
                ToolExecutionEvent(
                    event_type="tool_completed",
                    tool_name=tool_name,
                    duration_ms=duration_ms,
                    success=True,
                    summary=f"Successfully executed {tool_name} ({duration_ms:.1f}ms)",
                ),
            )

        except AppError as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.warning(f"AppError executing {tool_name}: {e.message}")
            return (
                ToolResult(
                    tool_name=tool_name,
                    success=False,
                    error=e.message,
                    data={"error_code": e.code.value, "details": e.details},
                ),
                ToolExecutionEvent(
                    event_type="tool_failed",
                    tool_name=tool_name,
                    duration_ms=duration_ms,
                    success=False,
                    error_code=e.code.value,
                    summary=f"Tool error in {tool_name}: {e.message}",
                ),
            )

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"Unexpected error executing {tool_name}: {e}", exc_info=True)
            return (
                ToolResult(
                    tool_name=tool_name,
                    success=False,
                    error="Internal tool execution error.",
                ),
                ToolExecutionEvent(
                    event_type="tool_failed",
                    tool_name=tool_name,
                    duration_ms=duration_ms,
                    success=False,
                    error_code=ErrorCode.INTERNAL_ERROR.value,
                    summary=f"Unexpected failure executing {tool_name}",
                ),
            )


# Default executor singleton
tool_executor = ToolExecutor()
