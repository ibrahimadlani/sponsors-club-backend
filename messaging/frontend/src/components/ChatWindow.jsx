import React from 'react';
import MessageInput from './MessageInput.jsx';

function formatTimestamp(value) {
  if (!value) {
    return '';
  }
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short'
    }).format(new Date(value));
  } catch (error) {
    return value;
  }
}

function ConnectionStatus({ status }) {
  const indicatorClass = status === 'connected' ? 'connection-indicator connected' : 'connection-indicator';
  let label = 'Not connected';
  if (status === 'connected') {
    label = 'Connected to WebSocket';
  } else if (status === 'connecting') {
    label = 'Connecting…';
  } else if (status === 'reconnecting') {
    label = 'Reconnecting…';
  } else if (status === 'error') {
    label = 'Connection error';
  }
  return (
    <div className="connection-bar">
      <span className={indicatorClass} />
      <span>{label}</span>
    </div>
  );
}

export default function ChatWindow({
  thread,
  messages,
  socketStatus,
  onSendMessage,
  currentUserId,
  loading
}) {
  if (!thread) {
    return (
      <section className="chat-panel">
        <div className="empty-state">Select a thread to start testing the messaging flow.</div>
      </section>
    );
  }

  return (
    <section className="chat-panel">
      <header>
        <h2 style={{ margin: 0 }}>{thread.collaborator?.user} ↔ {thread.agent?.display_name || thread.agent?.user}</h2>
        {thread.athlete ? <p style={{ margin: '0.25rem 0 0', color: '#64748b' }}>Athlete: {thread.athlete.full_name}</p> : null}
        <ConnectionStatus status={socketStatus} />
      </header>
      <div className="message-list">
        {loading ? (
          <div className="empty-state" style={{ boxShadow: 'none' }}>Loading messages…</div>
        ) : messages.length === 0 ? (
          <div className="empty-state" style={{ boxShadow: 'none' }}>No messages yet.</div>
        ) : (
          messages.map((message) => {
            const isSelf = currentUserId ? message.sender === currentUserId : false;
            return (
              <div key={message.id} className={`message${isSelf ? ' self' : ''}`}>
                {message.content ? <div>{message.content}</div> : null}
                {message.attachment ? (
                  <div className="attachment">
                    <span>Attachment:</span>
                    <a href={message.attachment} target="_blank" rel="noreferrer">
                      {message.attachment}
                    </a>
                  </div>
                ) : null}
                <time>{formatTimestamp(message.created_at)}</time>
                <span className="status">{message.is_read ? 'Read' : 'Unread'}</span>
              </div>
            );
          })
        )}
      </div>
      <MessageInput onSend={onSendMessage} disabled={socketStatus === 'connecting'} />
    </section>
  );
}
