import React, { useState } from 'react';

export default function MessageInput({ onSend, disabled }) {
  const [content, setContent] = useState('');
  const [attachment, setAttachment] = useState(null);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!content.trim() && !attachment) {
      return;
    }
    try {
      await onSend({ content: content.trim(), attachment });
    } catch (error) {
      // Swallow errors so the playground stays responsive; the parent surface handles feedback.
    }
    setContent('');
    setAttachment(null);
    event.target.reset();
  };

  return (
    <form className="message-input" onSubmit={handleSubmit}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        <textarea
          placeholder="Write a message…"
          value={content}
          onChange={(event) => setContent(event.target.value)}
          disabled={disabled}
        />
        <input
          type="file"
          onChange={(event) => setAttachment(event.target.files?.[0] || null)}
          disabled={disabled}
        />
      </div>
      <button type="submit" disabled={disabled}>
        Send
      </button>
    </form>
  );
}
