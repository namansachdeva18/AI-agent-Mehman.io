"""Conversation and session management service.

Handles:
- Persistent SQLite storage for conversations and ordered messages
- Incremental, validated BookingState updates with explicit overrides
- Optimistic locking using version column for lost update prevention
- Hold reconciliation (verifies active holds against booking_holds table)
- Session lifecycle: create, get, append message, update state, close
"""

from __future__ import annotations

from datetime import UTC, date, datetime
import json
import sqlite3
from typing import Any
import uuid

from pydantic import ValidationError

from app.agent.schemas import (
    BookingState,
    ChatMessage,
    ConversationState,
    ConversationStatus,
    MessageRole,
)
from app.database.connection import Database, get_db
from app.errors import AppError, ErrorCode


class ConversationService:
    """Service layer managing persistent conversations and incremental booking state."""

    def __init__(self, db: Database | None = None) -> None:
        self._db = db

    def _get_db(self) -> Database:
        return self._db or get_db()

    def create_conversation(
        self,
        conversation_id: str | None = None,
        initial_booking: BookingState | None = None,
    ) -> ConversationState:
        """Create a new persistent conversation session."""
        db = self._get_db()
        conv_id = conversation_id or f"conv-{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC)
        now_iso = now.isoformat()
        booking_data = initial_booking or BookingState()
        booking_json = booking_data.model_dump_json()

        try:
            with db:
                db.execute(
                    """
                    INSERT INTO conversations (
                        id, status, booking_state_json, current_hold_id, version, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        conv_id,
                        ConversationStatus.ACTIVE.value,
                        booking_json,
                        booking_data.hold_id,
                        now_iso,
                        now_iso,
                    ),
                )
        except sqlite3.IntegrityError as e:
            raise AppError(
                code=ErrorCode.INVALID_REQUEST,
                message=f"Conversation with ID '{conv_id}' already exists.",
                status_code=409,
            ) from e
        except sqlite3.Error as e:
            raise AppError(
                code=ErrorCode.DATABASE_ERROR,
                message="Failed to create conversation.",
                status_code=500,
                details={"error": str(e)},
            ) from e

        return ConversationState(
            session_id=conv_id,
            status=ConversationStatus.ACTIVE,
            messages=[],
            booking=booking_data,
            current_hold_id=booking_data.hold_id,
            version=1,
            created_at=now,
            updated_at=now,
        )

    def get_conversation(self, conversation_id: str) -> ConversationState:
        """Retrieve a conversation session, its ordered messages, and reconciled booking state."""
        db = self._get_db()
        try:
            with db:
                # 1. Fetch conversation row
                row = db.execute(
                    """
                    SELECT id, status, booking_state_json, current_hold_id, version, created_at, updated_at
                    FROM conversations
                    WHERE id = ?
                    """,
                    (conversation_id,),
                ).fetchone()

                if not row:
                    raise AppError(
                        code=ErrorCode.UNKNOWN_INFORMATION,
                        message=f"Conversation '{conversation_id}' not found.",
                        status_code=404,
                    )

                # 2. Fetch ordered messages
                msg_rows = db.execute(
                    """
                    SELECT id, role, content, sequence_number, metadata_json, created_at
                    FROM conversation_messages
                    WHERE conversation_id = ?
                    ORDER BY sequence_number ASC
                    """,
                    (conversation_id,),
                ).fetchall()

                messages: list[ChatMessage] = []
                for m in msg_rows:
                    meta = {}
                    if m["metadata_json"]:
                        try:
                            meta = json.loads(m["metadata_json"])
                        except Exception:
                            meta = {}
                    messages.append(
                        ChatMessage(
                            id=m["id"],
                            role=MessageRole(m["role"]),
                            content=m["content"],
                            sequence_number=int(m["sequence_number"]),
                            metadata=meta,
                            timestamp=datetime.fromisoformat(m["created_at"]),
                        )
                    )

                # 3. Parse booking state
                raw_json = row["booking_state_json"] or "{}"
                booking_dict = json.loads(raw_json)
                booking_state = BookingState.model_validate(booking_dict)

                # 4. Hold reconciliation: verify active hold still valid in DB
                hold_id = row["current_hold_id"] or booking_state.hold_id
                if hold_id:
                    hold_row = db.execute(
                        "SELECT id, status, expires_at FROM booking_holds WHERE id = ?",
                        (hold_id,),
                    ).fetchone()

                    if not hold_row or hold_row["status"] != "HELD":
                        # Hold is cancelled, expired, or missing: clear from active state
                        booking_state.hold_id = None
                        booking_state.hold_total_price = None
                        booking_state.hold_expires_at = None
                        hold_id = None
                    else:
                        # Check expiration timestamp against UTC now
                        expires_at = datetime.fromisoformat(hold_row["expires_at"])
                        if expires_at <= datetime.now(UTC):
                            booking_state.hold_id = None
                            booking_state.hold_total_price = None
                            booking_state.hold_expires_at = None
                            hold_id = None

                return ConversationState(
                    session_id=row["id"],
                    status=ConversationStatus(row["status"]),
                    messages=messages,
                    booking=booking_state,
                    current_hold_id=hold_id,
                    version=int(row["version"]),
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                )

        except AppError:
            raise
        except sqlite3.Error as e:
            raise AppError(
                code=ErrorCode.DATABASE_ERROR,
                message="Database error loading conversation.",
                status_code=500,
                details={"error": str(e)},
            ) from e

    def append_message(
        self,
        conversation_id: str,
        role: MessageRole,
        content: str,
        metadata: dict | None = None,
    ) -> ChatMessage:
        """Append a chat message to the conversation history with sequential ordering."""
        db = self._get_db()
        now = datetime.now(UTC)
        now_iso = now.isoformat()
        meta_json = json.dumps(metadata or {})

        try:
            with db:
                # Verify conversation exists
                conv = db.execute(
                    "SELECT id FROM conversations WHERE id = ?",
                    (conversation_id,),
                ).fetchone()

                if not conv:
                    raise AppError(
                        code=ErrorCode.UNKNOWN_INFORMATION,
                        message=f"Conversation '{conversation_id}' not found.",
                        status_code=404,
                    )

                # Compute next sequence number
                seq_row = db.execute(
                    "SELECT COALESCE(MAX(sequence_number), 0) + 1 as next_seq FROM conversation_messages WHERE conversation_id = ?",
                    (conversation_id,),
                ).fetchone()
                next_seq = int(seq_row["next_seq"])

                cursor = db.execute(
                    """
                    INSERT INTO conversation_messages (
                        conversation_id, role, content, sequence_number, metadata_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (conversation_id, role.value, content, next_seq, meta_json, now_iso),
                )
                msg_id = cursor.lastrowid

                # Update conversation updated_at
                db.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?",
                    (now_iso, conversation_id),
                )

                return ChatMessage(
                    id=msg_id,
                    role=role,
                    content=content,
                    sequence_number=next_seq,
                    metadata=metadata or {},
                    timestamp=now,
                )

        except AppError:
            raise
        except sqlite3.Error as e:
            raise AppError(
                code=ErrorCode.DATABASE_ERROR,
                message="Failed to append message to conversation.",
                status_code=500,
                details={"error": str(e)},
            ) from e

    def update_booking_state(
        self,
        conversation_id: str,
        updates: dict[str, Any] | BookingState,
        expected_version: int | None = None,
    ) -> ConversationState:
        """Incrementally update the booking state with validation and optimistic locking."""
        db = self._get_db()
        now_iso = datetime.now(UTC).isoformat()

        # Convert updates to dict
        if isinstance(updates, BookingState):
            patch_dict = updates.model_dump(exclude_unset=True)
        else:
            patch_dict = dict(updates)

        try:
            with db:
                # 1. Fetch current state and version
                row = db.execute(
                    """
                    SELECT id, status, booking_state_json, current_hold_id, version, created_at, updated_at
                    FROM conversations
                    WHERE id = ?
                    """,
                    (conversation_id,),
                ).fetchone()

                if not row:
                    raise AppError(
                        code=ErrorCode.UNKNOWN_INFORMATION,
                        message=f"Conversation '{conversation_id}' not found.",
                        status_code=404,
                    )

                current_version = int(row["version"])
                if expected_version is not None and expected_version != current_version:
                    raise AppError(
                        code=ErrorCode.INVALID_REQUEST,
                        message=f"Optimistic lock conflict: current version is {current_version}, expected {expected_version}.",
                        status_code=409,
                    )

                # 2. Merge existing state with patch
                raw_json = row["booking_state_json"] or "{}"
                current_state_dict = json.loads(raw_json)

                # Apply updates (non-None values override; explicit None can clear if passed)
                for k, v in patch_dict.items():
                    if k in BookingState.model_fields:
                        # Parse date strings if necessary
                        if k in ("check_in", "check_out") and isinstance(v, str):
                            try:
                                v = date.fromisoformat(v)
                            except ValueError as val_err:
                                raise AppError(
                                    code=ErrorCode.INVALID_DATES,
                                    message=f"Invalid date format for {k}: {v}. Expected YYYY-MM-DD.",
                                    status_code=400,
                                ) from val_err
                        current_state_dict[k] = v

                # 3. Deterministic state validation
                try:
                    new_booking = BookingState.model_validate(current_state_dict)
                except ValidationError as val_err:
                    err_msg = str(val_err)
                    if "Check-out date" in err_msg or "check_out" in err_msg:
                        raise AppError(
                            code=ErrorCode.INVALID_DATES,
                            message="Check-out date must be strictly after check-in date.",
                            status_code=400,
                        ) from val_err
                    raise AppError(
                        code=ErrorCode.INVALID_REQUEST,
                        message=f"State validation error: {err_msg}",
                        status_code=400,
                    ) from val_err

                # Database relationship validation
                if new_booking.selected_property_id is not None:
                    prop = db.execute(
                        "SELECT id, name FROM properties WHERE id = ?",
                        (new_booking.selected_property_id,),
                    ).fetchone()
                    if not prop:
                        raise AppError(
                            code=ErrorCode.UNKNOWN_INFORMATION,
                            message=f"Selected property ID {new_booking.selected_property_id} does not exist.",
                            status_code=400,
                        )
                    new_booking.selected_property_name = prop["name"]

                if new_booking.selected_room_id is not None:
                    rm = db.execute(
                        "SELECT id, property_id, name FROM rooms WHERE id = ?",
                        (new_booking.selected_room_id,),
                    ).fetchone()
                    if not rm:
                        raise AppError(
                            code=ErrorCode.UNKNOWN_INFORMATION,
                            message=f"Selected room ID {new_booking.selected_room_id} does not exist.",
                            status_code=400,
                        )
                    if (
                        new_booking.selected_property_id is not None
                        and rm["property_id"] != new_booking.selected_property_id
                    ):
                        raise AppError(
                            code=ErrorCode.INVALID_REQUEST,
                            message=(
                                f"Selected room '{rm['name']}' does not belong to "
                                f"property ID {new_booking.selected_property_id}."
                            ),
                            status_code=400,
                        )
                    new_booking.selected_room_name = rm["name"]

                # 4. Save with optimistic lock check
                new_json = new_booking.model_dump_json()
                new_hold_id = new_booking.hold_id

                cursor = db.execute(
                    """
                    UPDATE conversations
                    SET booking_state_json = ?,
                        current_hold_id = ?,
                        version = version + 1,
                        updated_at = ?
                    WHERE id = ? AND version = ?
                    """,
                    (new_json, new_hold_id, now_iso, conversation_id, current_version),
                )

                if cursor.rowcount == 0:
                    raise AppError(
                        code=ErrorCode.INVALID_REQUEST,
                        message=f"Concurrent modification conflict: version changed during update.",
                        status_code=409,
                    )

            # Return updated conversation
            return self.get_conversation(conversation_id)

        except AppError:
            raise
        except sqlite3.Error as e:
            raise AppError(
                code=ErrorCode.DATABASE_ERROR,
                message="Failed to update booking state in database.",
                status_code=500,
                details={"error": str(e)},
            ) from e

    def get_missing_search_fields(self, conversation_id: str) -> list[str]:
        """Return list of missing required search fields for the conversation."""
        conv = self.get_conversation(conversation_id)
        return conv.booking.get_missing_search_fields()

    def close_conversation(
        self,
        conversation_id: str,
        status: ConversationStatus = ConversationStatus.COMPLETED,
    ) -> None:
        """Close or abandon a conversation session."""
        db = self._get_db()
        now_iso = datetime.now(UTC).isoformat()
        try:
            with db:
                cursor = db.execute(
                    """
                    UPDATE conversations
                    SET status = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (status.value, now_iso, conversation_id),
                )
                if cursor.rowcount == 0:
                    raise AppError(
                        code=ErrorCode.UNKNOWN_INFORMATION,
                        message=f"Conversation '{conversation_id}' not found.",
                        status_code=404,
                    )
        except AppError:
            raise
        except sqlite3.Error as e:
            raise AppError(
                code=ErrorCode.DATABASE_ERROR,
                message="Failed to close conversation.",
                status_code=500,
                details={"error": str(e)},
            ) from e


# Singleton service helper
conversation_service = ConversationService()
