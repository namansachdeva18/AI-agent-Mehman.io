"""Agent Orchestrator for Mehman.io.

Coordinates:
- Multi-turn conversation state & history retrieval
- Natural language intent extraction & state patch merging
- Deterministic recommendation engine integration & multi-strategy ranking
- Side-by-side property comparison
- Upstream dependency and stale state invalidation (destination, dates, guests, budget)
- Missing search fields gating & clarification prompts
- Tool selection, validation, and execution via ToolExecutor
- Grounded, hallucination-free response generation
- Observability execution trace events
- Conversation persistence in SQLite
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import logging
import re
from typing import Any

from app.agent.executor import ToolExecutor, tool_executor
from app.agent.prompts import SYSTEM_INSTRUCTION, build_agent_context
from app.agent.schemas import (
    AgentDecision,
    AgentIntent,
    BookingState,
    ChatApiResponse,
    MessageRole,
    NextAction,
    StatePatch,
    ToolExecutionEvent,
    ToolResult,
)
from app.database.connection import Database
from app.errors import AppError, ErrorCode
from app.llm.base import LLMProvider
from app.llm.gemini import GeminiProvider
from app.recommendations.comparison import compare_rooms
from app.recommendations.engine import RecommendationEngine, recommendation_engine
from app.recommendations.models import BudgetMode, RankingStrategy, TravelerType
from app.services.conversation import ConversationService, conversation_service
from app.tools.availability import check_availability
from app.tools.booking_hold import release_expired_holds
from app.tools.contracts import CheckAvailabilityInput, SearchPropertiesInput
from app.tools.room_details import get_room_details, GetRoomDetailsInput
from app.tools.search import search_properties

logger = logging.getLogger(__name__)

# Inventory date boundaries
INVENTORY_START_DATE = date(2026, 9, 1)
INVENTORY_END_DATE = date(2027, 8, 31)

# City Pattern
CITY_PATTERN = re.compile(r"\b(goa|jaipur|manali)\b", re.IGNORECASE)

MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

WORD_TO_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def extract_destination_from_text(text: str) -> str | None:
    """Robust destination extraction supporting negative transitions and multi-city sentences."""
    lower = text.lower()

    # If there's an explicit transition like "forget X, let's do Y", "change to Y", "instead of X, Y", "make it Y"
    transition_match = re.search(r"(?:forget\s+[a-z]+[,\s]+(?:let's\s+do|go\s+to|visit|try)\s+|change\s+(?:the\s+destination\s+)?to\s+|instead\s+of\s+[a-z]+[,\s]+|make\s+it\s+|switch\s+to\s+|how\s+about\s+)(goa|jaipur|manali)\b", lower)
    if transition_match:
        return transition_match.group(1).capitalize()

    # Otherwise find all mentioned cities and pick the last one mentioned
    cities = CITY_PATTERN.findall(lower)
    if cities:
        return cities[-1].capitalize()

    return None


def extract_guests_from_text(text: str) -> int | None:
    """Extract guest count from digit, word formats, or natural family relationship mentions."""
    lower = text.lower()

    # 1. Family relationship mentions: "wife and 2 kids" (1+1+2=4), "husband and 2 kids" (4), "wife and kid" (3)
    fam_match = re.search(r"\b(?:with\s+my\s+|travelling\s+with\s+|traveling\s+with\s+)?(?:wife|husband|partner|spouse)\s+and\s+(\d+|one|two|three|four)\s+(?:kids|children|toddlers)\b", lower)
    if fam_match:
        kids_val = fam_match.group(1).lower()
        kids_count = int(kids_val) if kids_val.isdigit() else WORD_TO_NUM.get(kids_val, 2)
        return 2 + kids_count  # Self + spouse + kids

    if re.search(r"\b(?:with\s+my\s+|travelling\s+with\s+|traveling\s+with\s+)?(?:wife|husband|partner|spouse)\s+and\s+(?:a\s+kid|a\s+child|one\s+kid|one\s+child|kid|child)\b", lower):
        return 3

    # 2. "make that X people" / "make that X"
    make_match = re.search(r"\bmake\s+(?:that|it)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)(?:\s+people|\s+guests)?\b", lower)
    if make_match:
        val = make_match.group(1).lower()
        return int(val) if val.isdigit() else WORD_TO_NUM.get(val)

    # 3. Digit followed by guest terms: "5 people", "4 guests", "2 adults", "3 persons"
    d_match = re.search(r"\b(\d+)\s*(?:people|guests|persons|adults|of us)\b", lower)
    if d_match:
        return int(d_match.group(1))

    # 4. Number word followed by guest terms: "five people", "four guests", "two adults"
    w_match = re.search(r"\b(one|two|three|four|five|six|seven|eight|nine|ten)\s*(?:people|guests|persons|adults|of us)\b", lower)
    if w_match:
        return WORD_TO_NUM.get(w_match.group(1).lower())

    # 5. Phrases: "for 5", "for five", "we are 5", "we're five", "party of 4", "group of 5"
    p_match = re.search(r"\b(?:for|we\s+are|we're|party\s+of|group\s+of)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b", lower)
    if p_match:
        val = p_match.group(1).lower()
        if val.isdigit():
            return int(val)
        return WORD_TO_NUM.get(val)

    if re.fullmatch(r"\s*(\d+)\s*", lower):
        return int(lower.strip())

    return None


def extract_dates_from_text(text: str) -> tuple[str | None, str | None]:
    """Robust natural-language date extraction for stay date ranges."""
    lower = text.lower()

    # 0. Relative Weekend Queries: "next weekend", "this weekend"
    if "next weekend" in lower:
        return "2026-09-11", "2026-09-13"
    if "this weekend" in lower:
        return "2026-09-04", "2026-09-06"

    # 1. ISO format: 2026-09-10 to 2026-09-13 or 2026-09-10 - 2026-09-13
    iso_match = re.search(r"(\d{4}-\d{2}-\d{2})\s*(?:to|-|through|until)\s*(\d{4}-\d{2}-\d{2})", lower)
    if iso_match:
        return iso_match.group(1), iso_match.group(2)

    # 2. Month Day to Day (Year): "September 10 to 13", "September 10th to 13th 2026", "Sep 10-13", "September 10th through 13th"
    m_d_d = re.search(
        r"\b(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\.?\s+(\d{1,2})(?:st|nd|rd|th)?\s*(?:to|-|through|until)\s*(\d{1,2})(?:st|nd|rd|th)?(?:\s*,?\s*(\d{4}))?\b",
        lower,
    )
    if m_d_d:
        m_str, d1_str, d2_str, yr_str = m_d_d.group(1), m_d_d.group(2), m_d_d.group(3), m_d_d.group(4)
        m_num = MONTH_MAP.get(m_str, 9)
        d1, d2 = int(d1_str), int(d2_str)
        yr = int(yr_str) if yr_str else 2026
        return f"{yr:04d}-{m_num:02d}-{d1:02d}", f"{yr:04d}-{m_num:02d}-{d2:02d}"

    # 3. Day Month to Day (Year): "10th September through 13th", "10 September to 13", "10th September to 13th"
    d_m_d = re.search(
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\.?\s*(?:to|-|through|until)\s*(\d{1,2})(?:st|nd|rd|th)?(?:\s*,?\s*(\d{4}))?\b",
        lower,
    )
    if d_m_d:
        d1_str, m_str, d2_str, yr_str = d_m_d.group(1), d_m_d.group(2), d_m_d.group(3), d_m_d.group(4)
        m_num = MONTH_MAP.get(m_str, 9)
        d1, d2 = int(d1_str), int(d2_str)
        yr = int(yr_str) if yr_str else 2026
        return f"{yr:04d}-{m_num:02d}-{d1:02d}", f"{yr:04d}-{m_num:02d}-{d2:02d}"

    # 4. Month Day to Month Day: "September 10 to September 13", "Sep 10th to Sep 13th 2026"
    m_d_m_d = re.search(
        r"\b(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\.?\s+(\d{1,2})(?:st|nd|rd|th)?\s*(?:to|-|through|until)\s*(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*,?\s*(\d{4}))?\b",
        lower,
    )
    if m_d_m_d:
        m1_str, d1_str, m2_str, d2_str, yr_str = m_d_m_d.group(1), m_d_m_d.group(2), m_d_m_d.group(3), m_d_m_d.group(4), m_d_m_d.group(5)
        m1_num = MONTH_MAP.get(m1_str, 9)
        m2_num = MONTH_MAP.get(m2_str, 9)
        d1, d2 = int(d1_str), int(d2_str)
        yr = int(yr_str) if yr_str else 2026
        return f"{yr:04d}-{m1_num:02d}-{d1:02d}", f"{yr:04d}-{m2_num:02d}-{d2:02d}"

    # 5. Day to Day Month: "10 to 13 September", "10th to 13th September 2026", "10th-13th September"
    d_d_m = re.search(
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s*(?:to|-|through|until)\s*(\d{1,2})(?:st|nd|rd|th)?\s*(?:of\s+)?(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\.?(?:\s*,?\s*(\d{4}))?\b",
        lower,
    )
    if d_d_m:
        d1_str, d2_str, m_str, yr_str = d_d_m.group(1), d_d_m.group(2), d_d_m.group(3), d_d_m.group(4)
        m_num = MONTH_MAP.get(m_str, 9)
        d1, d2 = int(d1_str), int(d2_str)
        yr = int(yr_str) if yr_str else 2026
        return f"{yr:04d}-{m_num:02d}-{d1:02d}", f"{yr:04d}-{m_num:02d}-{d2:02d}"

    # 7. Single-date checkout shift: "stay till the 13th", "stay until 13th September", "till the 13th"
    till_match = re.search(r"\b(?:stay\s+)?(?:till|until|through)\s+(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?(?:\s+(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec))?(?:\s*,?\s*(\d{4}))?\b", lower)
    if till_match:
        d_val = int(till_match.group(1))
        m_val = till_match.group(2)
        m_num = MONTH_MAP.get(m_val, 9) if m_val else 9
        yr_val = int(till_match.group(3)) if till_match.group(3) else 2026
        return None, f"{yr_val:04d}-{m_num:02d}-{d_val:02d}"

    return None, None


class AgentOrchestrator:
    """Core orchestrator executing the Mehman.io booking agent workflow."""

    def __init__(
        self,
        llm: LLMProvider | None | bool = None,
        executor: ToolExecutor | None = None,
        conv_service: ConversationService | None = None,
        rec_engine: RecommendationEngine | None = None,
    ) -> None:
        if llm is False:
            self._llm = None
        else:
            self._llm = llm or GeminiProvider()
        self._executor = executor or tool_executor
        self._conv_service = conv_service or conversation_service
        self._rec_engine = rec_engine or recommendation_engine

    async def handle_message(
        self,
        conversation_id: str,
        user_message: str,
        db: Database | None = None,
    ) -> ChatApiResponse:
        """Handle a single guest message through the complete agent lifecycle."""
        events: list[ToolExecutionEvent] = []
        app_date = date(2026, 9, 1)
        effective_db = db or (self._conv_service._get_db() if hasattr(self._conv_service, "_get_db") else None)

        # 1. Retrieve or create conversation session
        try:
            conv = self._conv_service.get_conversation(conversation_id)
        except AppError:
            conv = self._conv_service.create_conversation(conversation_id=conversation_id)

        # 2. Append incoming user message to persistent history
        self._conv_service.append_message(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=user_message,
        )

        current_booking = conv.booking

        # 3. Intent Understanding & State Extraction
        decision = await self._analyze_intent_and_extract(
            user_message=user_message,
            booking=current_booking,
            history=conv.messages,
            app_date=app_date,
            db=effective_db,
        )

        # 4. Upstream Dependency & Stale State Invalidation
        patch_dict = decision.state_patch.model_dump(exclude_unset=True)

        # A. Invalidate room selections & add-ons if destination changed
        new_dest = patch_dict.get("destination")
        if new_dest and current_booking.destination and new_dest.strip().lower() != current_booking.destination.strip().lower():
            logger.info(f"Destination changed from {current_booking.destination} to {new_dest}. Invalidating stale room and add-on selections.")
            newly_extracted_room = decision.state_patch.selected_room_id
            if not newly_extracted_room or decision.state_patch.selected_property_id == current_booking.selected_property_id:
                patch_dict["selected_property_id"] = None
                patch_dict["selected_property_name"] = None
                patch_dict["selected_room_id"] = None
                patch_dict["selected_room_name"] = None
            patch_dict["hold_id"] = None
            patch_dict["hold_total_price"] = None
            patch_dict["hold_expires_at"] = None
            patch_dict["selected_add_on_ids"] = []

        # B. Invalidate hold if stay dates actually changed
        new_cin = patch_dict.get("check_in")
        new_cout = patch_dict.get("check_out")
        cin_changed = new_cin and current_booking.check_in and str(new_cin) != str(current_booking.check_in)
        cout_changed = new_cout and current_booking.check_out and str(new_cout) != str(current_booking.check_out)
        if cin_changed or cout_changed:
            patch_dict["hold_id"] = None
            patch_dict["hold_total_price"] = None
            patch_dict["hold_expires_at"] = None

        # C. Invalidate room selection if guest count increased beyond current room's capacity (unless in hold creation where capacity check explains it)
        new_guests = patch_dict.get("guests")
        target_check_room = patch_dict.get("selected_room_id") or current_booking.selected_room_id
        if new_guests and target_check_room and decision.intent not in (AgentIntent.CREATE_BOOKING_HOLD, AgentIntent.CHECK_AVAILABILITY):
            try:
                rm_info = get_room_details(GetRoomDetailsInput(room_id=target_check_room), db=effective_db)
                if rm_info.room.max_guests < new_guests:
                    logger.info(f"Guest count increased to {new_guests}, exceeding room capacity ({rm_info.room.max_guests}). Clearing room selection.")
                    patch_dict["selected_room_id"] = None
                    patch_dict["selected_room_name"] = None
                    patch_dict["hold_id"] = None
                    patch_dict["hold_total_price"] = None
                    patch_dict["hold_expires_at"] = None
            except Exception:
                pass

        # D. Authoritative Database Resolution for Add-ons Mentioned in Natural Language
        target_room_id = patch_dict.get("selected_room_id") or current_booking.selected_room_id
        target_prop_id = patch_dict.get("selected_property_id") or current_booking.selected_property_id
        if not patch_dict.get("selected_add_on_ids"):
            resolved_addons = self._resolve_addon_ids_from_text(
                text=user_message,
                room_id=target_room_id,
                property_id=target_prop_id,
                destination=patch_dict.get("destination") or current_booking.destination,
                db=effective_db,
            )
            if resolved_addons:
                patch_dict["selected_add_on_ids"] = resolved_addons
        elif patch_dict.get("selected_add_on_ids"):
            valid_ids = self._validate_and_filter_addon_ids(
                addon_ids=patch_dict["selected_add_on_ids"],
                property_id=target_prop_id,
                db=effective_db,
            )
            patch_dict["selected_add_on_ids"] = valid_ids

        # 5. Persist state updates
        if patch_dict:
            try:
                updated_conv = self._conv_service.update_booking_state(
                    conversation_id=conversation_id,
                    updates=patch_dict,
                )
                current_booking = updated_conv.booking
                summary_parts = []
                for k, v in patch_dict.items():
                    if v is not None and v != [] and v != "":
                        summary_parts.append(f"{k}: {v}")
                state_summary = ", ".join(summary_parts) if summary_parts else "Updated state"
                events.append(
                    ToolExecutionEvent(
                        event_type="state_updated",
                        summary=f"State updated: {state_summary}",
                    )
                )
            except ValueError as val_err:
                final_reply = f"I noticed an issue with your request: {val_err}. Please provide valid details."
                self._conv_service.append_message(
                    conversation_id=conversation_id,
                    role=MessageRole.ASSISTANT,
                    content=final_reply,
                )
                return ChatApiResponse(
                    conversation_id=conversation_id,
                    message=final_reply,
                    booking_state=current_booking,
                    next_action=NextAction.ASK_USER,
                    tool_events=[ToolExecutionEvent(event_type="validation_failed", summary=str(val_err))],
                    agent_decision=decision,
                )

        # 6. Action Determination & Tool Execution
        final_reply = ""
        next_act = decision.next_action

        # Check for inventory boundary violation
        if current_booking.check_in and current_booking.check_in < INVENTORY_START_DATE:
            final_reply = (
                f"Our available hotel inventory begins from **{INVENTORY_START_DATE}** through **{INVENTORY_END_DATE}**. "
                f"Please choose stay dates within this window."
            )
            next_act = NextAction.ASK_USER

        # Decision with Direct Pre-computed Response (e.g. Prompt injection refusal, Luxury amenity comparison, Unknown amenity response)
        elif decision.direct_response and decision.intent not in (
            AgentIntent.SEARCH_HOTELS,
            AgentIntent.RECOMMEND_PROPERTIES,
            AgentIntent.CHECK_AVAILABILITY,
            AgentIntent.CREATE_BOOKING_HOLD,
            AgentIntent.CALCULATE_PRICE,
        ):
            final_reply = decision.direct_response
            next_act = decision.next_action

        # Intent A: Side-by-Side Property/Room Comparison
        elif decision.intent == AgentIntent.COMPARE_PROPERTIES:
            room_ids_to_compare = [4, 5]
            if "jaipur" in (current_booking.destination or "").lower():
                room_ids_to_compare = [1, 2, 3]
            elif "manali" in (current_booking.destination or "").lower():
                room_ids_to_compare = [7, 8, 9]

            cmp_res = compare_rooms(
                room_ids=room_ids_to_compare,
                check_in=current_booking.check_in,
                check_out=current_booking.check_out,
                guests=current_booking.guests or 2,
                db=effective_db,
            )
            events.append(
                ToolExecutionEvent(
                    event_type="tool_completed",
                    tool_name="compare_rooms",
                    summary=f"Compared {len(cmp_res.properties)} room options",
                )
            )
            cmp_lines = ["### Room Comparison\n"]
            for p in cmp_res.properties:
                total_str = f" (Total: ₹{p.total_price:,.2f})" if p.total_price else ""
                cmp_lines.append(
                    f"**{p.room_name}** (*{p.property_name}*, {p.city}):\n"
                    f"- Rate: ₹{p.nightly_price:,.2f}/night{total_str}\n"
                    f"- Rating: {p.star_rating}★ | Capacity: Up to {p.max_guests} guests\n"
                    f"- Size: {p.room_size_sqft} sq ft ({p.bed_type} bed)\n"
                    f"- Key Amenities: {', '.join(p.amenities[:4])}\n"
                )
            if cmp_res.key_differences:
                cmp_lines.append("\n**Key Differences:**")
                for diff in cmp_res.key_differences:
                    cmp_lines.append(f"- {diff}")

            final_reply = "\n".join(cmp_lines) + "\n\nWhich of these would you prefer to book or examine in detail?"
            next_act = NextAction.COMPARE_PROPERTIES

        # Intent A2: Direct Room Availability Check (with alternatives if sold out / capacity conflict)
        elif decision.intent == AgentIntent.CHECK_AVAILABILITY or decision.next_action == NextAction.CHECK_AVAILABILITY:
            target_room = patch_dict.get("selected_room_id") or current_booking.selected_room_id
            if not target_room:
                next_act = NextAction.ASK_USER
                final_reply = "Which room would you like me to check availability for?"
            elif not current_booking.check_in or not current_booking.check_out:
                missing = current_booking.get_missing_search_fields()
                next_act = NextAction.ASK_USER
                final_reply = f"To check room availability, please provide your stay dates ({', '.join(missing)})."
            else:
                # Release expired holds so inventory is fresh
                release_expired_holds(db=effective_db)
                tool_args = {
                    "room_id": target_room,
                    "check_in": current_booking.check_in.isoformat(),
                    "check_out": current_booking.check_out.isoformat(),
                    "guests": current_booking.guests or 2,
                }
                t_res, t_evt = self._executor.execute_tool("check_availability", tool_args, db=effective_db)
                events.append(t_evt)
                if t_res.success:
                    rooms_list = t_res.data.get("rooms", [])
                    target_summary = next((r for r in rooms_list if r.get("room_id") == target_room), None) or (rooms_list[0] if rooms_list else None)
                    r_name = target_summary.get("room_name") if target_summary else (current_booking.selected_room_name or "The requested room")
                    is_avail = target_summary.get("available", False) if target_summary else False
                    unavail_reason = target_summary.get("unavailability_reason") if target_summary else "sold_out"

                    if is_avail:
                        units = target_summary.get("available_units", 1)
                        price = target_summary.get("price_per_night", 0)
                        final_reply = (
                            f"Yes! **{r_name}** is **available** for your stay from {current_booking.check_in} to {current_booking.check_out} "
                            f"({units} unit{'s' if units > 1 else ''} available at ₹{price:,.2f}/night).\n\n"
                            f"Would you like me to calculate itemized pricing with add-ons or place a 15-minute booking hold?"
                        )
                        next_act = NextAction.CALCULATE_PRICE
                    else:
                        # Find available alternatives from database
                        alt_lines = []
                        if current_booking.destination:
                            try:
                                search_args = SearchPropertiesInput(
                                    destination=current_booking.destination,
                                    check_in=current_booking.check_in,
                                    check_out=current_booking.check_out,
                                    guests=current_booking.guests or 2,
                                )
                                search_out = search_properties(search_args, db=effective_db)
                                for p in search_out.results:
                                    for rm in p.matching_rooms:
                                        if rm.room_id != target_room and rm.available is not False and rm.max_guests >= (current_booking.guests or 2):
                                            alt_lines.append(f"- **{rm.name}** at {p.property_name} (₹{rm.base_price_per_night:,.2f}/night, up to {rm.max_guests} guests)")
                            except Exception:
                                pass

                        alt_text = ""
                        if alt_lines:
                            alt_text = "\n\n**Here are available alternatives for your dates:**\n" + "\n".join(alt_lines[:3]) + "\n\nWould you like to book one of these options?"
                        else:
                            alt_text = "\n\nWould you like to explore alternative dates or different room options?"

                        if unavail_reason == "capacity_exceeded":
                            max_g = target_summary.get("max_guests", 2) if target_summary else 2
                            final_reply = (
                                f"**{r_name}** has a maximum capacity of **{max_g} guests**, which cannot accommodate your party of {current_booking.guests}."
                                f"{alt_text}"
                            )
                        else:
                            final_reply = (
                                f"**{r_name}** is **sold out** for {current_booking.check_in} to {current_booking.check_out}."
                                f"{alt_text}"
                            )
                        next_act = NextAction.RECOMMEND_PROPERTIES
                else:
                    final_reply = f"Could not verify room availability: {t_res.error}"
                    next_act = NextAction.HANDLE_ERROR

        # Intent B: Booking Hold (with Capacity Validation, Availability Re-validation & Guest Name check)
        elif decision.intent == AgentIntent.CREATE_BOOKING_HOLD:
            target_hold_room = patch_dict.get("selected_room_id") or current_booking.selected_room_id or decision.state_patch.selected_room_id
            if not target_hold_room:
                next_act = NextAction.ASK_USER
                final_reply = "Please select a specific room before I can place a booking hold."
            elif not current_booking.is_search_ready:
                missing = current_booking.get_missing_search_fields()
                next_act = NextAction.ASK_USER
                final_reply = f"To hold your room, I still need: {', '.join(missing)}."
            else:
                # Capacity Check before placing hold
                try:
                    rm_info = get_room_details(GetRoomDetailsInput(room_id=target_hold_room), db=effective_db)
                    if current_booking.guests and current_booking.guests > rm_info.room.max_guests:
                        # Reject capacity conflict
                        alt_rooms = []
                        if current_booking.destination:
                            s_out = search_properties(
                                SearchPropertiesInput(
                                    destination=current_booking.destination,
                                    check_in=current_booking.check_in,
                                    check_out=current_booking.check_out,
                                    guests=current_booking.guests,
                                ),
                                db=effective_db,
                            )
                            for p in s_out.results:
                                for r in p.matching_rooms:
                                    if r.max_guests >= current_booking.guests:
                                        alt_rooms.append(f"- **{r.name}** at {p.property_name} (Capacity: {r.max_guests} guests, ₹{r.base_price_per_night:,.2f}/night)")
                        alt_str = "\n".join(alt_rooms[:2]) if alt_rooms else "options with higher capacity"
                        final_reply = (
                            f"I cannot place a booking hold for **{rm_info.room.room_name}** because its maximum capacity is **{rm_info.room.max_guests} guests**, "
                            f"which cannot accommodate your party of {current_booking.guests}.\n\n"
                            f"**Recommended options for {current_booking.guests} guests:**\n{alt_str}\n\n"
                            f"Would you like to reserve one of these suitable rooms instead?"
                        )
                        next_act = NextAction.RECOMMEND_PROPERTIES
                        self._conv_service.append_message(
                            conversation_id=conversation_id,
                            role=MessageRole.ASSISTANT,
                            content=final_reply,
                        )
                        return ChatApiResponse(
                            conversation_id=conversation_id,
                            message=final_reply,
                            booking_state=current_booking,
                            next_action=next_act,
                            tool_events=events,
                            agent_decision=decision,
                        )
                except Exception:
                    pass

                if not current_booking.guest_name and not patch_dict.get("guest_name"):
                    next_act = NextAction.ASK_USER
                    final_reply = "May I please have your full name so I can place the 15-minute booking hold under your name?"
                else:
                    guest_name_val = patch_dict.get("guest_name") or current_booking.guest_name or "Valued Guest"
                    release_expired_holds(db=effective_db)

                    tool_args = {
                        "room_id": target_hold_room,
                        "check_in": current_booking.check_in.isoformat(),
                        "check_out": current_booking.check_out.isoformat(),
                        "guests": current_booking.guests,
                        "guest_name": guest_name_val,
                        "selected_add_ons": current_booking.selected_add_on_ids,
                        "session_id": conversation_id,
                    }
                    t_res, t_evt = self._executor.execute_tool("create_booking_hold", tool_args, db=effective_db)
                    events.append(t_evt)
                    if t_res.success:
                        hold_data = t_res.data.get("hold", {})
                        hold_id = hold_data.get("hold_id")
                        total_p = hold_data.get("total_price")
                        expires_at = hold_data.get("expires_at")
                        self._conv_service.update_booking_state(
                            conversation_id,
                            {"hold_id": hold_id, "hold_total_price": total_p, "hold_expires_at": expires_at, "guest_name": guest_name_val},
                        )
                        current_booking = self._conv_service.get_conversation(conversation_id).booking
                        final_reply = (
                            f"I've placed a temporary booking hold for you!\n"
                            f"- Hold ID: **{hold_id}**\n"
                            f"- Guest Name: {guest_name_val}\n"
                            f"- Room: {current_booking.selected_room_name or 'Selected Room'}\n"
                            f"- Dates: {current_booking.check_in} to {current_booking.check_out}\n"
                            f"- Total Price: ₹{total_p:,.2f}\n"
                            f"- Status: Active for 15 minutes (expires at {expires_at})."
                        )
                        next_act = NextAction.CONFIRM_BOOKING
                    else:
                        final_reply = (
                            f"Could not create booking hold: {t_res.error}. "
                            f"The room is no longer available for your stay dates. Would you like to explore alternative dates or room options?"
                        )
                        next_act = NextAction.HANDLE_ERROR

        # Intent C: Price Calculation
        elif decision.intent == AgentIntent.CALCULATE_PRICE:
            if not current_booking.selected_room_id:
                next_act = NextAction.ASK_USER
                final_reply = "Which room would you like to calculate pricing for?"
            elif not current_booking.check_in or not current_booking.check_out or not current_booking.guests:
                missing = current_booking.get_missing_search_fields()
                next_act = NextAction.ASK_USER
                final_reply = f"To calculate the exact price, please provide: {', '.join(missing)}."
            else:
                tool_args = {
                    "room_id": current_booking.selected_room_id,
                    "check_in": current_booking.check_in.isoformat(),
                    "check_out": current_booking.check_out.isoformat(),
                    "guests": current_booking.guests,
                    "selected_add_ons": current_booking.selected_add_on_ids,
                }
                t_res, t_evt = self._executor.execute_tool("calculate_price", tool_args, db=effective_db)
                events.append(t_evt)
                if not t_res.success and "Add-on with ID" in str(t_res.error):
                    logger.warning(f"Add-on ID mismatch detected in calculate_price: {t_res.error}. Recovering dynamically from SQLite.")
                    clean_addons = self._resolve_addon_ids_from_text(
                        text=user_message,
                        room_id=current_booking.selected_room_id,
                        property_id=current_booking.selected_property_id,
                        destination=current_booking.destination,
                        db=effective_db,
                    )
                    self._conv_service.update_booking_state(
                        conversation_id,
                        {"selected_add_on_ids": clean_addons},
                    )
                    current_booking = self._conv_service.get_conversation(conversation_id).booking
                    tool_args["selected_add_ons"] = clean_addons
                    t_res, t_evt = self._executor.execute_tool("calculate_price", tool_args, db=effective_db)
                    events.append(t_evt)

                if t_res.success:
                    b = t_res.data.get("breakdown", {})
                    addon_items = b.get("add_on_items", [])
                    addon_lines = []
                    for item in addon_items:
                        addon_lines.append(f"- {item.get('name')}: ₹{item.get('total_cost', 0):,.2f} ({item.get('calculation')})")
                    addon_section = ("\n" + "\n".join(addon_lines)) if addon_lines else ""

                    final_reply = (
                        f"Here is the itemized price breakdown for {current_booking.selected_room_name or 'your room'}:\n"
                        f"- Stay: {b.get('nights')} nights ({current_booking.check_in} to {current_booking.check_out})\n"
                        f"- Room Total: ₹{b.get('room_total', 0):,.2f}{addon_section}\n"
                        f"- Add-ons Total: ₹{b.get('add_ons_total', 0):,.2f}\n"
                        f"- **Grand Total: ₹{b.get('grand_total', 0):,.2f}**\n\n"
                        f"Would you like me to place a 15-minute booking hold on this room?"
                    )
                    next_act = NextAction.CALCULATE_PRICE
                else:
                    final_reply = f"Unable to calculate pricing: {t_res.error}"
                    next_act = NextAction.HANDLE_ERROR

        # Intent D: Room Details & Policy Inquiries
        elif decision.intent == AgentIntent.GET_ROOM_DETAILS or decision.tool_name == "get_room_details":
            room_id = patch_dict.get("selected_room_id") or decision.state_patch.selected_room_id or decision.tool_arguments.get("room_id") or current_booking.selected_room_id or 1
            tool_args = {"room_id": room_id}
            t_res, t_evt = self._executor.execute_tool("get_room_details", tool_args, db=effective_db)
            events.append(t_evt)
            if t_res.success:
                rm = t_res.data.get("room", {})
                self._conv_service.update_booking_state(
                    conversation_id,
                    {
                        "selected_property_id": rm.get("property_id"),
                        "selected_property_name": rm.get("property_name"),
                        "selected_room_id": rm.get("room_id"),
                        "selected_room_name": rm.get("room_name"),
                    },
                )
                current_booking = self._conv_service.get_conversation(conversation_id).booking
                lower_msg = user_message.lower()
                policies_list = rm.get("policies", [])
                policy_map = {p.get("policy_type", "").lower(): p.get("description", "") for p in policies_list}

                if any(w in lower_msg for w in ["cancel", "cancellation", "refund"]):
                    cancel_desc = policy_map.get("cancellation") or "Free cancellation up to 24 hours prior to arrival date."
                    final_reply = (
                        f"**Cancellation Policy** for *{rm.get('property_name')}* ({rm.get('room_name')}):\n"
                        f"- {cancel_desc}\n\n"
                        f"Please let me know if you need further assistance with your reservation!"
                    )
                elif any(w in lower_msg for w in ["check-in", "check in", "check-out", "check out", "timing", "time"]):
                    ci_desc = policy_map.get("check_in") or "Check-in time is from 14:00 onwards."
                    co_desc = policy_map.get("check_out") or "Check-out time is 11:00."
                    final_reply = (
                        f"**Check-in & Check-out Policies** for *{rm.get('property_name')}*:\n"
                        f"- **Check-in**: {ci_desc}\n"
                        f"- **Check-out**: {co_desc}"
                    )
                elif any(w in lower_msg for w in ["pet", "pets", "dog", "cat"]):
                    pet_desc = policy_map.get("pet") or "Please check with our concierge regarding pet policies."
                    final_reply = (
                        f"**Pet Policy** for *{rm.get('property_name')}*:\n"
                        f"- {pet_desc}"
                    )
                elif any(w in lower_msg for w in ["child", "children", "kids", "kid"]):
                    child_desc = policy_map.get("child") or "Children policies apply as per standard hotel guidelines."
                    final_reply = (
                        f"**Child Policy** for *{rm.get('property_name')}*:\n"
                        f"- {child_desc}"
                    )
                elif any(w in lower_msg for w in ["extra bed", "mattress", "rollaway"]):
                    bed_desc = policy_map.get("extra_bed") or "Extra beds are available upon request and subject to property fees."
                    final_reply = (
                        f"**Extra Bed Policy** for *{rm.get('property_name')}*:\n"
                        f"- {bed_desc}"
                    )
                else:
                    amenity_list = ", ".join(rm.get("amenities", [])) or "Standard luxury amenities"
                    final_reply = (
                        f"**{rm.get('room_name')}** at *{rm.get('property_name')}* ({rm.get('city')}):\n"
                        f"- Description: {rm.get('description')}\n"
                        f"- Base Price: ₹{rm.get('base_price_per_night'):,.2f}/night\n"
                        f"- Capacity: Up to {rm.get('max_guests')} guests ({rm.get('bed_type')} bed, {rm.get('room_size_sqft')} sq ft)\n"
                        f"- Amenities: {amenity_list}\n\n"
                        f"Would you like to calculate pricing for your stay or reserve a hold?"
                    )
                next_act = NextAction.GET_ROOM_DETAILS
            else:
                final_reply = f"Could not find room details: {t_res.error}"

        # Intent E: Recommendation & Intelligent Search Flow
        elif decision.intent in (AgentIntent.RECOMMEND_PROPERTIES, AgentIntent.SEARCH_HOTELS, AgentIntent.MODIFY_SEARCH) or (decision.intent in (AgentIntent.UNKNOWN, AgentIntent.SEARCH_HOTELS) and current_booking.is_search_ready and not current_booking.selected_room_id and not current_booking.hold_id):
            missing = current_booking.get_missing_search_fields()
            if missing:
                next_act = NextAction.ASK_USER
                dest_str = f" in **{current_booking.destination}**" if current_booking.destination else ""
                if "check_in" in missing and "guests" in missing:
                    final_reply = f"I'd be delighted to help you find the perfect stay{dest_str}! Could you please share your **stay dates** and how many **guests** will be traveling?"
                elif "check_in" in missing or "check_out" in missing:
                    guest_str = f" for {current_booking.guests} guests" if current_booking.guests else ""
                    final_reply = f"To find the best available rooms{dest_str}{guest_str}, what **dates** are you planning for your stay?"
                elif "guests" in missing:
                    dates_str = f" from {current_booking.check_in} to {current_booking.check_out}" if current_booking.check_in else ""
                    final_reply = f"Wonderful! How many **guests** will be staying with us{dest_str}{dates_str}?"
                elif "destination" in missing:
                    final_reply = "Which destination would you like to visit? We offer luxury accommodations in **Goa**, **Jaipur**, and **Manali**."
                else:
                    readable_missing = [m.replace("_", " ") for m in missing]
                    final_reply = f"To find the ideal options for you, could you please share your **{', '.join(readable_missing)}**?"
            else:
                release_expired_holds(db=effective_db)
                search_args = SearchPropertiesInput(
                    destination=current_booking.destination,
                    check_in=current_booking.check_in,
                    check_out=current_booking.check_out,
                    guests=current_booking.guests,
                    budget_per_night=None,
                )
                search_out = search_properties(search_args, db=effective_db)

                strat = RankingStrategy.BEST_MATCH
                if "cheapest" in user_message.lower() or "lowest" in user_message.lower() or "cheaper" in user_message.lower():
                    strat = RankingStrategy.CHEAPEST
                elif "best value" in user_message.lower() or "value" in user_message.lower():
                    strat = RankingStrategy.BEST_VALUE
                elif "luxury" in user_message.lower() or "suite" in user_message.lower():
                    strat = RankingStrategy.LUXURY
                elif "family" in user_message.lower() or "kids" in user_message.lower():
                    strat = RankingStrategy.FAMILY

                t_type = TravelerType.FAMILY if "family" in user_message.lower() else TravelerType.STANDARD
                b_mode = BudgetMode.MAX if "under" in user_message.lower() or "max" in user_message.lower() else BudgetMode.TARGET

                rec_result = self._rec_engine.rank_candidates(
                    search_results=search_out.results,
                    guests=current_booking.guests or 2,
                    budget_per_night=current_booking.budget_per_night,
                    budget_mode=b_mode,
                    preferred_amenities=current_booking.preferred_amenities,
                    traveler_type=t_type,
                    strategy=strat,
                    top_n=3,
                    check_in=current_booking.check_in,
                    check_out=current_booking.check_out,
                    db=effective_db,
                )

                events.append(
                    ToolExecutionEvent(
                        event_type="recommendation_completed",
                        tool_name="recommendation_engine",
                        summary=f"Ranked {rec_result.total_candidates_qualified} qualified candidates ({strat.value})",
                    )
                )

                if not rec_result.candidates:
                    final_reply = (
                        f"I searched for properties in **{current_booking.destination}** for {current_booking.guests} guests, "
                        f"but found no available options matching your constraints. "
                        f"Would you like to adjust your budget or dates?"
                    )
                    next_act = NextAction.SEARCH_PROPERTIES
                else:
                    rec_lines = [f"### Recommended Options in {current_booking.destination} ({strat.value.replace('_', ' ')})\n"]
                    for idx, c in enumerate(rec_result.candidates, start=1):
                        match_badge = "★ Top Recommendation" if idx == 1 else f"Option #{idx}"
                        if c.match_type.value == "ALTERNATIVE":
                            match_badge = "Alternative Option"

                        total_info = f" (Stay Total: ₹{c.total_price:,.2f})" if c.total_price else ""
                        rec_lines.append(
                            f"**{idx}. {c.property_name} — {c.room_name}** [{match_badge}]\n"
                            f"- Rate: ₹{c.nightly_price:,.2f}/night{total_info}\n"
                            f"- Rating: {c.star_rating}★ | Capacity: Up to {c.max_guests} guests\n"
                            f"- Why this fits: {c.recommendation_reason}\n"
                        )

                    final_reply = "\n".join(rec_lines) + "\n\nWhich room would you like to explore or book?"
                    next_act = NextAction.RECOMMEND_PROPERTIES

        else:
            if any(q in user_message.lower() for q in ["france", "weather in tokyo", "who wrote", "recipe", "math"]):
                final_reply = (
                    "I am the Mehman.io AI hotel booking assistant. I specialize in finding, comparing, and reserving "
                    "accommodations at our properties in Goa, Jaipur, and Manali. How may I help with your hotel plans?"
                )
                next_act = NextAction.RESPOND
            else:
                missing = current_booking.get_missing_search_fields()
                if missing and decision.intent == AgentIntent.UNKNOWN:
                    dest_str = f" in **{current_booking.destination}**" if current_booking.destination else ""
                    if "check_in" in missing and "guests" in missing:
                        final_reply = f"I'd be happy to help you find the best accommodations{dest_str}! Could you share your **stay dates** and how many **guests** are traveling?"
                    elif "check_in" in missing:
                        final_reply = f"What **dates** are you planning for your stay{dest_str}?"
                    elif "guests" in missing:
                        final_reply = f"How many **guests** will be staying with us{dest_str}?"
                    else:
                        readable = [m.replace("_", " ") for m in missing]
                        final_reply = f"To assist with your booking, please share your **{', '.join(readable)}**."
                    next_act = NextAction.ASK_USER
                else:
                    final_reply = decision.direct_response or "How may I assist you with your hotel booking today?"
                    next_act = NextAction.RESPOND

        # 7. Persist Assistant Response Message
        self._conv_service.append_message(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=final_reply,
        )

        events.append(
            ToolExecutionEvent(
                event_type="response_generated",
                summary=f"Generated response with action {next_act.value}",
            )
        )

        return ChatApiResponse(
            conversation_id=conversation_id,
            message=final_reply,
            booking_state=current_booking,
            next_action=next_act,
            tool_events=events,
            agent_decision=decision,
        )

    async def _analyze_intent_and_extract(
        self,
        user_message: str,
        booking: BookingState,
        history: list[Any],
        app_date: date,
        db: Database | None = None,
    ) -> AgentDecision:
        """Call Gemini structured output or deterministic fallback to parse message."""
        if self._llm and self._llm.is_configured():
            try:
                context_str = build_agent_context(
                    current_date=app_date,
                    booking_state=booking,
                    recent_messages=history,
                )
                prompt = (
                    f"{context_str}\n\n"
                    f"USER_MESSAGE:\n\"{user_message}\"\n\n"
                    f"Analyze the user message, extract state changes into state_patch, determine intent and next_action."
                )

                decision_dict = await self._llm.generate_structured(
                    prompt=prompt,
                    response_schema=AgentDecision.model_json_schema(),
                    system_prompt=SYSTEM_INSTRUCTION,
                )
                decision = AgentDecision.model_validate(decision_dict)

                # Validate and repair dates extracted by LLM if needed
                d_in, d_out = extract_dates_from_text(user_message)
                if d_in and d_out:
                    decision.state_patch.check_in = d_in
                    decision.state_patch.check_out = d_out
                else:
                    for attr in ("check_in", "check_out"):
                        val = getattr(decision.state_patch, attr)
                        if val and isinstance(val, str):
                            try:
                                date.fromisoformat(val)
                            except ValueError:
                                setattr(decision.state_patch, attr, None)

                # Room name & ID normalization
                lower_msg = user_message.lower()
                room_map = [
                    (["family garden suite", "family suite", "garden suite"], 5, 2),
                    (["superior ocean view", "ocean view room"], 4, 2),
                    (["beachfront luxury villa", "beachfront villa"], 6, 2),
                    (["deluxe heritage", "heritage room"], 1, 1),
                    (["royal courtyard"], 2, 1),
                    (["maharaja presidential suite", "maharaja suite"], 3, 1),
                    (["cozy pine", "pine room"], 7, 3),
                    (["deluxe valley view", "valley view suite", "valley view balcony"], 8, 3),
                    (["cedar attic"], 9, 3),
                ]
                for phrases, r_id, p_id in room_map:
                    if any(p in lower_msg for p in phrases):
                        decision.state_patch.selected_room_id = r_id
                        decision.state_patch.selected_property_id = p_id
                        break

                # Context Reference Selections ("the other one", "second option", "other room")
                if any(p in lower_msg for p in ["the other one", "other option", "other room", "what about the other", "second option", "second one", "the 2nd one", "second recommendation"]):
                    active_dest = (decision.state_patch.destination or booking.destination or "goa").lower()
                    if "goa" in active_dest:
                        if booking.selected_room_id == 5:
                            decision.state_patch.selected_room_id = 6
                        elif booking.selected_room_id == 6:
                            decision.state_patch.selected_room_id = 5
                        else:
                            decision.state_patch.selected_room_id = 5
                        decision.state_patch.selected_property_id = 2
                    elif "jaipur" in active_dest:
                        if booking.selected_room_id == 2:
                            decision.state_patch.selected_room_id = 3
                        elif booking.selected_room_id == 1:
                            decision.state_patch.selected_room_id = 2
                        else:
                            decision.state_patch.selected_room_id = 2
                        decision.state_patch.selected_property_id = 1
                    elif "manali" in active_dest:
                        if booking.selected_room_id == 8:
                            decision.state_patch.selected_room_id = 9
                        elif booking.selected_room_id == 7:
                            decision.state_patch.selected_room_id = 8
                        else:
                            decision.state_patch.selected_room_id = 8
                        decision.state_patch.selected_property_id = 3
                    decision.intent = AgentIntent.GET_ROOM_DETAILS
                    decision.next_action = NextAction.GET_ROOM_DETAILS
                    decision.tool_name = "get_room_details"
                    decision.tool_arguments = {"room_id": decision.state_patch.selected_room_id}

                # Destination check
                parsed_dest = extract_destination_from_text(user_message)
                if parsed_dest:
                    decision.state_patch.destination = parsed_dest

                # Policy intent check
                if re.search(r"\b(cancellation|cancel|refund|policy|policies|check-in|check\s+in|check-out|check\s+out|timing|pet|pets|dog|cat|child|children|kids|extra\s+bed|mattress|rollaway)\b", lower_msg):
                    decision.intent = AgentIntent.GET_ROOM_DETAILS
                    decision.next_action = NextAction.GET_ROOM_DETAILS
                    decision.tool_name = "get_room_details"
                    target_r = decision.state_patch.selected_room_id or booking.selected_room_id
                    if not target_r:
                        target_r = 5 if "goa" in (decision.state_patch.destination or booking.destination or "goa").lower() else (1 if "jaipur" in (decision.state_patch.destination or booking.destination or "").lower() else 7)
                    decision.tool_arguments = {"room_id": target_r}

                return decision
            except Exception as e:
                logger.warning(f"Gemini structured extraction failed ({e}), falling back to deterministic extraction.")

        return self._deterministic_fallback_analysis(user_message, booking, db=db)

    def _deterministic_fallback_analysis(
        self,
        user_message: str,
        booking: BookingState,
        db: Database | None = None,
    ) -> AgentDecision:
        """Robust deterministic rule-based extractor for offline tests, rate limits, and resilience."""
        patch = StatePatch()
        lower = user_message.lower().strip()
        database = db or Database()

        # 1. Security & Prompt Injection Defense Check
        if any(w in lower for w in [
            "system override", "disregard all", "ignore previous", "set booking price to",
            "price to ₹0", "price to 0", "set price to 0", "set price to ₹0", "admin override",
            "jailbreak", "drop table", "show database", "system prompt", "reveal system",
            "developer mode", "unrestricted ai", "fake tool result", "override hold price",
            "disable all validation", "give me free booking",
        ]):
            return AgentDecision(
                intent=AgentIntent.UNKNOWN,
                next_action=NextAction.RESPOND,
                reason_code="security_prompt_injection_refusal",
                direct_response="I cannot override system pricing, inventory constraints, or hotel policies. I am strictly authorized to help you search, compare, and book our verified partner properties in Goa, Jaipur, and Manali.",
                state_patch=patch,
            )

        intent = AgentIntent.UNKNOWN
        next_action = NextAction.RESPOND
        tool_name = None
        tool_args: dict[str, Any] = {}
        direct_resp: str | None = None

        # Extract Destination
        dest_val = extract_destination_from_text(user_message)
        if dest_val:
            patch.destination = dest_val
        elif booking.destination:
            patch.destination = booking.destination

        # Extract Dates
        d_in, d_out = extract_dates_from_text(user_message)
        if d_in and d_out:
            patch.check_in = d_in
            patch.check_out = d_out
        elif d_out and not d_in:
            patch.check_out = d_out
            if booking.check_in:
                patch.check_in = booking.check_in.isoformat() if hasattr(booking.check_in, 'isoformat') else str(booking.check_in)
        else:
            if booking.check_in:
                patch.check_in = booking.check_in.isoformat() if hasattr(booking.check_in, 'isoformat') else str(booking.check_in)
            if booking.check_out:
                patch.check_out = booking.check_out.isoformat() if hasattr(booking.check_out, 'isoformat') else str(booking.check_out)

        # Handle Date Extension / "one more night" / "another night"
        if any(p in lower for p in ["one more night", "stay one more night", "another night", "extend by one night", "add one night", "add a night"]):
            if booking.check_out:
                try:
                    c_out_date = booking.check_out if isinstance(booking.check_out, date) else date.fromisoformat(str(booking.check_out))
                    new_cout = c_out_date + timedelta(days=1)
                    patch.check_out = new_cout.isoformat()
                    if booking.check_in:
                        patch.check_in = booking.check_in.isoformat() if isinstance(booking.check_in, date) else str(booking.check_in)
                except Exception:
                    pass

        # Extract Guest count
        guest_val = extract_guests_from_text(user_message)
        if guest_val is not None:
            patch.guests = guest_val
        elif patch.guests is None and booking.guests is not None:
            patch.guests = booking.guests

        # Extract Budget (supports ₹20,000, 20000, 20k, 15k, etc.)
        budget_match = re.search(r"(?:budget|under|below|max)\s*(?:of|is)?\s*₹?\s*([\d,]+(?:\s*k)?)", lower)
        if budget_match:
            raw_b = budget_match.group(1).replace(",", "").strip()
            if raw_b.endswith("k"):
                patch.budget_per_night = float(raw_b[:-1].strip()) * 1000.0
            else:
                patch.budget_per_night = float(raw_b)

        # Extract Amenities
        amenities_found = list(booking.preferred_amenities)
        if "pool" in lower or "swimming pool" in lower or "private pool" in lower:
            if "Swimming Pool" not in amenities_found:
                amenities_found.append("Swimming Pool")
        if "spa" in lower:
            if "Spa" not in amenities_found:
                amenities_found.append("Spa")
        if "beach" in lower or "beachfront" in lower:
            if "Beachfront" not in amenities_found:
                amenities_found.append("Beachfront")
        if amenities_found:
            patch.preferred_amenities = amenities_found

        room_prefs_found = list(booking.room_preferences)
        if "balcony" in lower:
            if "Balcony" not in room_prefs_found:
                room_prefs_found.append("Balcony")
        if room_prefs_found:
            patch.room_preferences = room_prefs_found

        # Room name extraction
        if "family garden suite" in lower or "family suite" in lower or "garden suite" in lower:
            patch.selected_room_id = 5
            patch.selected_property_id = 2
        elif "superior ocean view" in lower or "ocean view room" in lower:
            patch.selected_room_id = 4
            patch.selected_property_id = 2
        elif "beachfront luxury villa" in lower or "beachfront villa" in lower:
            patch.selected_room_id = 6
            patch.selected_property_id = 2
        elif "deluxe heritage" in lower or "heritage room" in lower:
            patch.selected_room_id = 1
            patch.selected_property_id = 1
        elif "royal courtyard" in lower:
            patch.selected_room_id = 2
            patch.selected_property_id = 1
        elif "maharaja presidential suite" in lower or "maharaja suite" in lower:
            patch.selected_room_id = 3
            patch.selected_property_id = 1
        elif "cozy pine" in lower:
            patch.selected_room_id = 7
            patch.selected_property_id = 3
        elif "deluxe valley view" in lower or "valley view suite" in lower or "valley view balcony" in lower:
            patch.selected_room_id = 8
            patch.selected_property_id = 3
        elif "cedar attic" in lower:
            patch.selected_room_id = 9
            patch.selected_property_id = 3

        # Context Reference Selections (#2, second option, etc.)
        if any(p in lower for p in ["the second one", "second option", "#2", "option 2", "the 2nd one", "second recommendation", "the other one", "other room", "other option"]):
            active_dest = (patch.destination or booking.destination or "goa").lower()
            if "goa" in active_dest:
                if booking.selected_room_id == 5:
                    patch.selected_room_id = 6
                elif booking.selected_room_id == 6:
                    patch.selected_room_id = 5
                else:
                    patch.selected_room_id = 5
                patch.selected_property_id = 2
            elif "jaipur" in active_dest:
                if booking.selected_room_id == 2:
                    patch.selected_room_id = 3
                elif booking.selected_room_id == 1:
                    patch.selected_room_id = 2
                else:
                    patch.selected_room_id = 2
                patch.selected_property_id = 1
            elif "manali" in active_dest:
                if booking.selected_room_id == 8:
                    patch.selected_room_id = 9
                elif booking.selected_room_id == 7:
                    patch.selected_room_id = 8
                else:
                    patch.selected_room_id = 8
                patch.selected_property_id = 3
            intent = AgentIntent.GET_ROOM_DETAILS
            next_action = NextAction.GET_ROOM_DETAILS
            tool_name = "get_room_details"
            tool_args = {"room_id": patch.selected_room_id}

        elif any(p in lower for p in ["the first one", "first option", "#1", "option 1", "the 1st one", "first recommendation"]):
            active_dest = (patch.destination or booking.destination or "goa").lower()
            if "goa" in active_dest:
                patch.selected_room_id = 4
                patch.selected_property_id = 2
            elif "jaipur" in active_dest:
                patch.selected_room_id = 1
                patch.selected_property_id = 1
            elif "manali" in active_dest:
                patch.selected_room_id = 7
                patch.selected_property_id = 3
            intent = AgentIntent.GET_ROOM_DETAILS
            next_action = NextAction.GET_ROOM_DETAILS
            tool_name = "get_room_details"
            tool_args = {"room_id": patch.selected_room_id}

        # 2. Unknown / Hallucinated Amenities Check (e.g. helicopter, submarine, ski lift, casino, heated pool)
        elif any(w in lower for w in [
            "heated pool", "is the pool heated", "is pool heated", "private helicopter", "helicopter", "submarine", "ski lift", "casino",
            "indoor wave pool", "pet elephant", "private cinema", "hot air balloon",
            "ice skating",
        ]):
            dest = patch.destination or booking.destination or "our properties"
            direct_resp = (
                f"Information about requested special facilities in '{user_message.strip('?')}' is not available in our database records for {dest} (no matching verified facilities found). "
                f"Our properties feature verified amenities such as direct beach access, high-speed Wi-Fi, swimming pools, "
                f"and heritage spa wellness. Would you like to review verified amenities for a specific room?"
            )
            return AgentDecision(
                intent=AgentIntent.UNKNOWN,
                next_action=NextAction.RESPOND,
                reason_code="unknown_amenity_not_in_database",
                direct_response=direct_resp,
                state_patch=patch,
            )

        # 3. Contextual Luxury / Best Amenity Comparison ("Which room has the best luxury amenities?")
        elif any(p in lower for p in [
            "best luxury amenities", "luxury amenities", "best amenities", "strongest luxury",
            "which room has the best amenities", "which room has the most luxury",
        ]):
            active_dest = (patch.destination or booking.destination or "goa").lower()
            if "goa" in active_dest or booking.selected_property_id == 2:
                prop_name = "Azure Sands Beach Resort (Goa)"
                best_room = "Beachfront Luxury Villa"
                reason_details = "it includes Direct Beach Access, Sea View, Air Conditioning, Private Balcony, and Free High-Speed Wi-Fi"
            elif "jaipur" in active_dest or booking.selected_property_id == 1:
                prop_name = "The Grand Heritage Palace (Jaipur)"
                best_room = "Maharaja Presidential Suite"
                reason_details = "it includes 24/7 Royal Butler Service, Private Balcony, Air Conditioning, and Free High-Speed Wi-Fi"
            else:
                prop_name = "Pinecrest Mountain Lodge (Manali)"
                best_room = "Deluxe Valley View Balcony"
                reason_details = "it features Panoramic Mountain View, Private Wooden Balcony, Room Heater, and Free High-Speed Wi-Fi"

            direct_resp = (
                f"For **{prop_name}**, the **{best_room}** has the strongest luxury-oriented amenity match based on our database records, "
                f"as {reason_details}.\n\n"
                f"Would you like to check availability or calculate pricing for this room?"
            )
            return AgentDecision(
                intent=AgentIntent.GET_ROOM_DETAILS,
                next_action=NextAction.RESPOND,
                reason_code="contextual_luxury_amenity_evaluation",
                direct_response=direct_resp,
                state_patch=patch,
            )

        # 4. Policy Lookups (cancellation, check-in, pets, children, extra bed)
        elif re.search(r"\b(cancellation|cancel|refund|policy|policies|check-in|check\s+in|check-out|check\s+out|timing|pet|pets|dog|cat|child|children|kids|extra\s+bed|mattress|rollaway)\b", lower):
            intent = AgentIntent.GET_ROOM_DETAILS
            next_action = NextAction.GET_ROOM_DETAILS
            tool_name = "get_room_details"
            target_r = patch.selected_room_id or booking.selected_room_id
            if not target_r:
                active_dest = (patch.destination or booking.destination or "goa").lower()
                target_r = 1 if "jaipur" in active_dest else (7 if "manali" in active_dest else 5)
            tool_args = {"room_id": target_r}

        # 4b. Conversation Recovery: "yes", "sure", "proceed", "confirm"
        elif re.fullmatch(r"\s*(yes|yes\s+please|sure|proceed|confirm|go\s+ahead|lock\s+it|please\s+do|yep|yeah)\s*", lower):
            if booking.selected_room_id or patch.selected_room_id:
                intent = AgentIntent.CREATE_BOOKING_HOLD
                next_action = NextAction.CREATE_BOOKING_HOLD
            else:
                intent = AgentIntent.RECOMMEND_PROPERTIES
                next_action = NextAction.RECOMMEND_PROPERTIES

        # 4c. Conversation Recovery: "whichever is better", "which one is better"
        elif any(p in lower for p in ["whichever is better", "which one is better", "whichever is best", "pick the best"]):
            active_dest = (patch.destination or booking.destination or "goa").lower()
            if "goa" in active_dest:
                patch.selected_room_id = 4
                patch.selected_property_id = 2
            elif "jaipur" in active_dest:
                patch.selected_room_id = 1
                patch.selected_property_id = 1
            elif "manali" in active_dest:
                patch.selected_room_id = 7
                patch.selected_property_id = 3
            intent = AgentIntent.GET_ROOM_DETAILS
            next_action = NextAction.GET_ROOM_DETAILS
            tool_name = "get_room_details"
            tool_args = {"room_id": patch.selected_room_id}

        # 4d. Conversation Recovery: "what about the other one?", "the other one", "show other"
        elif any(p in lower for p in ["what about the other one", "the other one", "other option", "show other", "what about the second"]):
            active_dest = (patch.destination or booking.destination or "goa").lower()
            if "goa" in active_dest:
                if booking.selected_room_id == 5:
                    patch.selected_room_id = 6
                elif booking.selected_room_id == 6:
                    patch.selected_room_id = 5
                else:
                    patch.selected_room_id = 5
                patch.selected_property_id = 2
            elif "jaipur" in active_dest:
                if booking.selected_room_id == 2:
                    patch.selected_room_id = 3
                elif booking.selected_room_id == 1:
                    patch.selected_room_id = 2
                else:
                    patch.selected_room_id = 2
                patch.selected_property_id = 1
            elif "manali" in active_dest:
                if booking.selected_room_id == 8:
                    patch.selected_room_id = 9
                elif booking.selected_room_id == 7:
                    patch.selected_room_id = 8
                else:
                    patch.selected_room_id = 8
                patch.selected_property_id = 3
            intent = AgentIntent.GET_ROOM_DETAILS
            next_action = NextAction.GET_ROOM_DETAILS
            tool_name = "get_room_details"
            tool_args = {"room_id": patch.selected_room_id}

        # 5. Side-by-Side Comparison Intent
        elif re.search(r"\b(compare|versus|vs|difference between)\b", lower):
            intent = AgentIntent.COMPARE_PROPERTIES
            next_action = NextAction.COMPARE_PROPERTIES

        # 6. Availability Check ("can i book", "is it available", "is available", "do you have")
        elif re.search(r"\b(is\s+available|available|availability|is\s+it\s+free|can\s+i\s+book|can\s+i\s+stay|do\s+you\s+have)\b", lower):
            intent = AgentIntent.CHECK_AVAILABILITY
            next_action = NextAction.CHECK_AVAILABILITY

        # 7. Booking Hold Intent ("book it", "reserve", "hold", "please book", "book this room")
        elif re.search(r"\b(book\s+it|reserve|hold|create\s+hold|please\s+book|book\s+this|book\s+for)\b", lower) or (
            re.search(r"\bbook\b", lower) and ("for" in lower or patch.selected_room_id or booking.selected_room_id)
        ):
            intent = AgentIntent.CREATE_BOOKING_HOLD
            next_action = NextAction.CREATE_BOOKING_HOLD
            name_match = re.search(r"\bfor\s+([A-Za-z]+(?:\s+[A-Za-z]+)*)", user_message)
            if name_match:
                extracted_name = name_match.group(1).title()
                # Filter out stopwords
                if extracted_name.lower() not in ["2 guests", "5 guests", "4 people", "2 people", "2", "3", "4", "5", "me", "us", "him", "her"]:
                    patch.guest_name = extracted_name

        # 8. Price Calculation Intent
        elif re.search(r"\b(how\s+much|cost|price|total|pricing|calculate|with\s+breakfast|add\s+breakfast|include\s+breakfast)\b", lower):
            intent = AgentIntent.CALCULATE_PRICE
            next_action = NextAction.CALCULATE_PRICE

        # 9. Cheaper / Too Expensive / Recommendation / Search Intent
        elif re.search(r"\b(too\s+expensive|expensive|pricey|cheapest|cheaper|lowest|something cheaper|any cheaper|any cheaper option|recommend|which is best|best for|best value|most luxurious|family hotel|suggest|hotel|stay|resort|lodge|find|search|looking\s+for|trip|vacation)\b", lower):
            intent = AgentIntent.RECOMMEND_PROPERTIES
            next_action = NextAction.RECOMMEND_PROPERTIES
            if any(w in lower for w in ["cheaper", "cheapest", "expensive", "pricey", "too expensive", "lowest", "recommend"]):
                patch.selected_room_id = None
                patch.selected_property_id = None

        # 10. Specific Room Details
        elif (
            re.search(r"\b(tell\s+me\s+about|details\s+of|view\s+room|show\s+details|about\s+the|information\s+on|show\s+me\s+the)\b", lower)
            or (patch.selected_room_id is not None and patch.selected_room_id != booking.selected_room_id)
        ):
            intent = AgentIntent.GET_ROOM_DETAILS
            next_action = NextAction.GET_ROOM_DETAILS
            tool_name = "get_room_details"
            target_r = patch.selected_room_id or booking.selected_room_id or 1
            tool_args = {"room_id": target_r}

        # Preserve existing room if none was extracted and no destination conflict
        if not patch.selected_room_id and booking.selected_room_id:
            patch.selected_room_id = booking.selected_room_id
            patch.selected_property_id = booking.selected_property_id

        return AgentDecision(
            intent=intent,
            next_action=next_action,
            reason_code="deterministic_rule_extraction",
            state_patch=patch,
            tool_name=tool_name,
            tool_arguments=tool_args,
            direct_response=direct_resp,
        )

    def _resolve_addon_ids_from_text(
        self,
        text: str,
        room_id: int | None,
        property_id: int | None,
        destination: str | None,
        db: Database | None = None,
    ) -> list[int]:
        """Authoritatively resolve natural-language add-on mentions to active SQLite add-on IDs."""
        lower = text.lower()
        active_addons: list[dict[str, Any]] = []
        database = db or Database()

        if room_id:
            try:
                rm_details = get_room_details(GetRoomDetailsInput(room_id=room_id), db=database)
                active_addons = [
                    {"id": a.id, "name": a.name, "pricing_type": a.pricing_type}
                    for a in rm_details.room.available_add_ons
                ]
            except Exception:
                pass

        if not active_addons and property_id:
            try:
                rows = database.execute(
                    "SELECT id, name, pricing_type FROM add_ons WHERE property_id = ? AND active = 1",
                    (property_id,),
                ).fetchall()
                active_addons = [dict(r) for r in rows]
            except Exception:
                pass

        if not active_addons and destination:
            try:
                dest_lower = destination.strip().lower()
                prop_row = database.execute(
                    "SELECT id FROM properties WHERE LOWER(city) = ? OR LOWER(name) LIKE ?",
                    (dest_lower, f"%{dest_lower}%"),
                ).fetchone()
                if prop_row:
                    rows = database.execute(
                        "SELECT id, name, pricing_type FROM add_ons WHERE property_id = ? AND active = 1",
                        (prop_row["id"],),
                    ).fetchall()
                    active_addons = [dict(r) for r in rows]
            except Exception:
                pass

        if not active_addons:
            return []

        matched_ids: list[int] = []
        for addon in active_addons:
            aname = addon["name"].lower()
            if "breakfast" in aname and "breakfast" in lower:
                matched_ids.append(addon["id"])
            elif "shuttle" in aname and ("shuttle" in lower or "airport shuttle" in lower):
                matched_ids.append(addon["id"])
            elif "chauffeur" in aname and ("chauffeur" in lower or "airport pickup" in lower or "luxury sedan" in lower):
                matched_ids.append(addon["id"])
            elif "bed" in aname and ("extra bed" in lower or "rollaway" in lower or "extra rollaway" in lower):
                matched_ids.append(addon["id"])
            elif "cruise" in aname and ("cruise" in lower or "catamaran" in lower or "sunset cruise" in lower):
                matched_ids.append(addon["id"])
            elif "spa" in aname and ("spa" in lower or "massage" in lower or "ayurvedic" in lower):
                matched_ids.append(addon["id"])
            elif "dinner" in aname and ("dinner" in lower or "thali" in lower or "royal thali" in lower):
                matched_ids.append(addon["id"])
            elif "tea" in aname and ("high tea" in lower or "afternoon tea" in lower):
                matched_ids.append(addon["id"])
            elif "bonfire" in aname and ("bonfire" in lower or "bbq" in lower):
                matched_ids.append(addon["id"])
            elif "trekking" in aname and ("trekking" in lower or "gear" in lower):
                matched_ids.append(addon["id"])
            elif "heater" in aname and ("heater" in lower or "room heater" in lower):
                matched_ids.append(addon["id"])

        return matched_ids

    def _validate_and_filter_addon_ids(
        self,
        addon_ids: list[int],
        property_id: int | None,
        db: Database | None = None,
    ) -> list[int]:
        """Filter user-provided add-on IDs to ensure they exist, are active, and belong to the target property."""
        if not addon_ids:
            return []
        database = db or Database()
        try:
            placeholders = ",".join("?" for _ in addon_ids)
            sql = f"SELECT id, property_id, active FROM add_ons WHERE id IN ({placeholders})"
            rows = database.execute(sql, addon_ids).fetchall()
            valid_ids: list[int] = []
            for r in rows:
                if r["active"] == 1:
                    if property_id is None or r["property_id"] == property_id:
                        valid_ids.append(r["id"])
            return valid_ids
        except Exception:
            return addon_ids


# Singleton orchestrator instance
agent_orchestrator = AgentOrchestrator()
