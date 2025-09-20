import React from 'react';

function formatParticipantSummary(thread) {
  const collaboratorName = thread?.collaborator?.user || 'Unknown collaborator';
  const agentName = thread?.agent?.display_name || thread?.agent?.user || 'Unknown agent';
  return `${collaboratorName} ↔ ${agentName}`;
}

function formatMessagePreview(message) {
  if (!message) {
    return 'No messages yet';
  }
  if (message.attachment) {
    return message.content ? `${message.content} · 📎 attachment` : '📎 Attachment';
  }
  return message.content || 'Untitled message';
}

export default function ThreadList({
  threads,
  selectedThreadId,
  onSelect,
  loading,
  onRefresh
}) {
  return (
    <aside className="sidebar">
      <header>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.5rem' }}>
          <span>Threads</span>
          <button type="button" onClick={onRefresh} disabled={loading}>
            Refresh
          </button>
        </div>
      </header>
      {loading ? (
        <div className="empty-state">Loading threads…</div>
      ) : threads.length === 0 ? (
        <div className="empty-state">No threads found for this user/token.</div>
      ) : (
        <ul className="thread-list">
          {threads.map((thread) => (
            <li
              key={thread.id}
              className={`thread-item${thread.id === selectedThreadId ? ' active' : ''}`}
              onClick={() => onSelect(thread)}
              role="presentation"
            >
              <h3>{formatParticipantSummary(thread)}</h3>
              <p>{formatMessagePreview(thread.last_message)}</p>
              {thread.athlete ? (
                <p style={{ color: '#0ea5e9' }}>Athlete: {thread.athlete.full_name}</p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
