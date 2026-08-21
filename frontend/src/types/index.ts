/**
 * TypeScript interfaces mirroring the backend Pydantic schemas.
 *
 * These types define the contract between frontend and backend.
 * They stay in strict synchronization with backend/app/agent/schemas.py
 * and backend/app/recommendations/models.py.
 */

// ============================================================
// Conversation Lifecycle & Session
// ============================================================

export type ConversationStatus = 'ACTIVE' | 'COMPLETED' | 'ABANDONED';

export type MessageRole = 'USER' | 'ASSISTANT' | 'SYSTEM' | 'TOOL' | 'guest' | 'agent';

export interface ChatMessage {
  id?: number;
  role: MessageRole;
  content: string;
  sequence_number?: number;
  metadata?: Record<string, unknown>;
  timestamp: string;
}

export type BudgetMode = 'MAX' | 'TARGET' | 'FLEXIBLE';
export type TravelerType = 'FAMILY' | 'COUPLE' | 'LUXURY' | 'BUDGET' | 'BUSINESS' | 'GROUP' | 'SOLO' | 'STANDARD';
export type RankingStrategy = 'BEST_MATCH' | 'CHEAPEST' | 'BEST_VALUE' | 'LUXURY' | 'FAMILY' | 'PRICE_LOW_TO_HIGH';

export interface BookingState {
  destination: string | null;
  check_in: string | null; // ISO date string (YYYY-MM-DD)
  check_out: string | null; // ISO date string (YYYY-MM-DD)
  guests: number | null;
  adults: number | null;
  children: number | null;
  budget_per_night: number | null;
  budget_mode?: BudgetMode | string;
  traveler_type?: TravelerType | string;
  preferred_amenities: string[];
  amenities?: string[];
  room_preferences: string[];
  special_requirements: string[];
  selected_property_id: number | null;
  selected_property_name: string | null;
  selected_room_id: number | null;
  selected_room_name: string | null;
  selected_add_on_ids: number[];
  guest_name?: string | null;
  hold_id: string | null;
  hold_total_price: number | null;
  hold_expires_at: string | null;
}

export interface ConversationState {
  session_id: string;
  status: ConversationStatus;
  messages: ChatMessage[];
  booking: BookingState;
  current_hold_id: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface StateResponse {
  session_id: string;
  version: number;
  booking: BookingState;
  missing_search_fields: string[];
  is_search_ready: boolean;
}

// ============================================================
// Tool Events & Chat Response
// ============================================================

export interface ToolExecutionEvent {
  event_type: string;
  tool_name?: string | null;
  duration_ms?: number | null;
  success: boolean;
  error_code?: string | null;
  summary: string;
  timestamp: string;
}

export interface ChatApiResponse {
  session_id: string;
  conversation_id: string;
  reply: string;
  message: string;
  booking_state: BookingState;
  next_action: string;
  tool_events: ToolExecutionEvent[];
  agent_implemented: boolean;
}

// ============================================================
// Hotel / Recommendation Types
// ============================================================

export interface ScoreBreakdown {
  preference_match: number;
  value_score: number;
  quality_score: number;
  capacity_fit: number;
  amenity_match: number;
  final_score: number;
}

export interface RecommendationCandidate {
  property_id: number;
  property_name: string;
  city: string;
  star_rating: number;
  room_id: number;
  room_name: string;
  room_size_sqft: number;
  bed_type: string;
  nightly_price: number;
  total_price: number | null;
  max_guests: number;
  available: boolean;
  matched_amenities: string[];
  unmatched_preferences: string[];
  match_type: 'EXACT_MATCH' | 'ALTERNATIVE';
  score_breakdown: ScoreBreakdown;
  recommendation_reason: string;
}

export interface AddOnItem {
  id: number;
  name: string;
  description: string;
  price: number;
  pricing_type: string; // PER_NIGHT, PER_BOOKING, PER_PERSON, PER_PERSON_PER_NIGHT
}

export interface HealthResponse {
  status: string;
  gemini_configured: boolean;
}
