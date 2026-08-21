import React from 'react';
import type { BookingState } from '../../types';
import type { ExecutionTraceData } from '../../hooks/useChat';

interface ExecutionTraceProps {
  trace: ExecutionTraceData | null;
  bookingState: BookingState | null;
  isSending?: boolean;
}

export const ExecutionTrace: React.FC<ExecutionTraceProps> = ({
  trace,
  bookingState,
  isSending = false,
}) => {
  // Format next action into clean human label
  const formatNextAction = (action?: string): string => {
    if (!action) return 'Awaiting user message';
    const map: Record<string, string> = {
      RECOMMEND_PROPERTIES: 'Recommend matching properties',
      SEARCH_HOTELS: 'Search hotel inventory',
      SEARCH_PROPERTIES: 'Explore property options',
      CALCULATE_PRICE: 'Calculate itemized stay pricing',
      GET_ROOM_DETAILS: 'Retrieve room details & policies',
      CREATE_BOOKING_HOLD: 'Create 15-minute booking hold',
      CONFIRM_BOOKING: 'Confirm booking hold active',
      COMPARE_PROPERTIES: 'Compare rooms side-by-side',
      CHECK_AVAILABILITY: 'Check unit availability',
      ASK_USER: 'Request missing information',
      RESPOND: 'Provide direct concierge answer',
      HANDLE_ERROR: 'Handle and explain error',
    };
    return map[action] || action.replace(/_/g, ' ').toLowerCase();
  };

  // State summary elements
  const stateItems: { label: string; value: string }[] = [];
  if (bookingState?.destination) {
    stateItems.push({ label: 'destination', value: bookingState.destination });
  }
  if (bookingState?.check_in && bookingState?.check_out) {
    stateItems.push({ label: 'dates', value: `${bookingState.check_in} → ${bookingState.check_out}` });
  }
  if (bookingState?.guests) {
    stateItems.push({ label: 'guests', value: `${bookingState.guests}` });
  }
  if (bookingState?.budget_per_night) {
    stateItems.push({ label: 'budget', value: `₹${bookingState.budget_per_night.toLocaleString('en-IN')}/night` });
  }
  if (bookingState?.selected_room_name) {
    stateItems.push({ label: 'selected room', value: bookingState.selected_room_name });
  }
  if (bookingState?.hold_id) {
    stateItems.push({ label: 'active hold', value: bookingState.hold_id });
  }

  const hasEvents = trace && trace.toolEvents && trace.toolEvents.length > 0;

  return (
    <div className="execution-trace-card" aria-label="Agent execution trace and activity panel">
      <div className="trace-header">
        <div className="trace-header-left">
          <span className="trace-pulse-dot" />
          <h5 className="trace-title">Execution Trace</h5>
        </div>
        <span className="trace-live-badge">
          {isSending ? 'Executing...' : 'Ready'}
        </span>
      </div>

      <div className="trace-body">
        {/* 1. STATE UPDATE */}
        <div className="trace-section">
          <div className="trace-section-header">
            <span className="trace-step-icon">✓</span>
            <span className="trace-step-title">State Context</span>
          </div>
          {stateItems.length > 0 ? (
            <div className="trace-state-grid">
              {stateItems.map((item) => (
                <div key={item.label} className="trace-state-item">
                  <span className="trace-state-label">{item.label}:</span>
                  <span className="trace-state-val">{item.value}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="trace-empty-hint">Awaiting search parameters...</div>
          )}
        </div>

        {/* 2. TOOL CALLS & RESULTS */}
        {hasEvents ? (
          <div className="trace-section">
            <div className="trace-section-header">
              <span className="trace-step-icon">⚙</span>
              <span className="trace-step-title">Tools & Verification</span>
            </div>
            <div className="trace-events-list">
              {trace.toolEvents.map((evt, idx) => {
                const isError = !evt.success || evt.event_type === 'tool_failed';
                const isState = evt.event_type === 'state_updated';
                const isResp = evt.event_type === 'response_generated';

                let icon = '✓';
                if (isError) icon = '✕';
                else if (isState) icon = '✦';
                else if (isResp) icon = '💬';

                return (
                  <div
                    key={`${evt.timestamp}-${idx}`}
                    className={`trace-event-item ${isError ? 'event-error' : ''}`}
                  >
                    <div className="trace-event-line">
                      <span className="event-bullet">{icon}</span>
                      {evt.tool_name ? (
                        <span className="event-tool-name">{evt.tool_name}()</span>
                      ) : (
                        <span className="event-category">{evt.event_type.replace(/_/g, ' ')}</span>
                      )}
                      {evt.duration_ms != null && (
                        <span className="event-duration">{evt.duration_ms.toFixed(1)}ms</span>
                      )}
                    </div>
                    {evt.summary && (
                      <div className="event-summary">{evt.summary}</div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          !isSending && (
            <div className="trace-section">
              <div className="trace-section-header">
                <span className="trace-step-icon">⚙</span>
                <span className="trace-step-title">Deterministic Tools</span>
              </div>
              <div className="trace-empty-hint">
                Tools run deterministically upon each guest inquiry.
              </div>
            </div>
          )
        )}

        {/* 3. ERROR (if any) */}
        {trace?.error && (
          <div className="trace-section trace-error-section">
            <div className="trace-section-header">
              <span className="trace-step-icon error">⚠</span>
              <span className="trace-step-title error">Execution Error</span>
            </div>
            <div className="trace-error-text">{trace.error}</div>
          </div>
        )}

        {/* 4. NEXT ACTION */}
        <div className="trace-section trace-next-action-section">
          <div className="trace-section-header">
            <span className="trace-step-icon action">→</span>
            <span className="trace-step-title">Next Action</span>
          </div>
          <div className="trace-next-action-badge">
            {formatNextAction(trace?.nextAction)}
          </div>
        </div>
      </div>
    </div>
  );
};
