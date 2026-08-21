import { useEffect, useState } from 'react';
import { BookingPanel } from './components/booking/BookingPanel';
import { ChatInput } from './components/chat/ChatInput';
import { MessageList } from './components/chat/MessageList';
import { SuggestedPrompts } from './components/chat/SuggestedPrompts';
import { Header } from './components/layout/Header';
import { Modal } from './components/layout/Modal';
import { useChat } from './hooks/useChat';
import { healthCheck } from './services/api';
import './styles/design-tokens.css';
import './App.css';

export function App() {
  const [apiOnline, setApiOnline] = useState(false);
  const [showNewStayModal, setShowNewStayModal] = useState(false);
  const [showMobilePanel, setShowMobilePanel] = useState(false);

  const {
    messages,
    bookingState,
    isSending,
    latestTrace,
    activeHold,
    sendMessage,
    startNewConversation,
    reconcileSession,
  } = useChat();

  useEffect(() => {
    healthCheck()
      .then(() => setApiOnline(true))
      .catch(() => setApiOnline(false));
  }, []);

  const handleNewStayClick = () => {
    if (activeHold) {
      setShowNewStayModal(true);
    } else {
      startNewConversation();
    }
  };

  const handleConfirmNewStay = () => {
    setShowNewStayModal(false);
    startNewConversation();
  };

  return (
    <div className="app-root">
      <Header
        hasActiveHold={Boolean(activeHold)}
        onNewConversation={handleNewStayClick}
        apiOnline={apiOnline}
        onToggleMobilePanel={() => setShowMobilePanel((prev) => !prev)}
        showMobilePanel={showMobilePanel}
      />

      <main className="app-layout">
        <section className="chat-panel" aria-label="Conversation with Mehman Concierge">
          <MessageList
            messages={messages}
            isSending={isSending}
            onQuickAction={sendMessage}
          />

          <SuggestedPrompts
            bookingState={bookingState}
            onSelectPrompt={sendMessage}
            disabled={isSending}
          />

          <ChatInput
            onSend={sendMessage}
            disabled={isSending}
          />
        </section>

        <BookingPanel
          bookingState={bookingState}
          trace={latestTrace}
          isSending={isSending}
          onQuickAction={(text) => {
            sendMessage(text);
            setShowMobilePanel(false);
          }}
          onExpire={reconcileSession}
          isOpenOnMobile={showMobilePanel}
          onCloseMobile={() => setShowMobilePanel(false)}
        />
      </main>

      <Modal
        isOpen={showNewStayModal}
        title="Active Hold in Progress"
        confirmText="Abandon Hold & Start New"
        cancelText="Keep Current Stay"
        isDanger={true}
        onConfirm={handleConfirmNewStay}
        onCancel={() => setShowNewStayModal(false)}
      >
        <p>
          You currently have a room locked on hold. Starting a new stay plan will leave this hold behind until its 15-minute window expires.
        </p>
        <p style={{ marginTop: '0.75rem', color: 'var(--text-secondary)' }}>
          Are you sure you want to proceed with a new conversation?
        </p>
      </Modal>
    </div>
  );
}

export default App;
