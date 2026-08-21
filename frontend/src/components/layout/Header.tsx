import React from 'react';

interface HeaderProps {
  hasActiveHold: boolean;
  onNewConversation: () => void;
  apiOnline: boolean;
  onToggleMobilePanel?: () => void;
  showMobilePanel?: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  hasActiveHold,
  onNewConversation,
  apiOnline,
  onToggleMobilePanel,
  showMobilePanel = false,
}) => {
  return (
    <header className="site-header">
      <div className="header-brand">
        <div className="brand-logo">
          <span className="logo-icon">✦</span>
          <span className="brand-name">Mehman<span className="brand-accent">.io</span></span>
        </div>
        <span className="brand-tagline">Mira — AI Luxury Hotel Concierge</span>
      </div>

      <div className="header-actions">
        <div className="status-badge" title={apiOnline ? "FastAPI Online" : "Connecting..."}>
          <span className={`status-dot ${apiOnline ? 'online' : 'offline'}`} />
          <span className="status-text">{apiOnline ? 'Connected' : 'Offline'}</span>
        </div>

        {onToggleMobilePanel && (
          <button
            type="button"
            className={`btn btn-secondary btn-sm mobile-only-btn ${showMobilePanel ? 'btn-active' : ''}`}
            onClick={onToggleMobilePanel}
            aria-label={showMobilePanel ? 'Hide trip plan' : 'Show trip plan'}
          >
            📋 {showMobilePanel ? 'Hide Plan' : 'Trip Plan'}
          </button>
        )}

        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={onNewConversation}
          title={hasActiveHold ? "Warning: active hold will be abandoned" : "Start a new conversation"}
          aria-label="Start new conversation"
        >
          <span className="btn-icon">+</span> New Stay
        </button>
      </div>
    </header>
  );
};

