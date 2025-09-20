import React, { useCallback, useEffect, useMemo, useState } from 'react';
import ThreadList from './components/ThreadList.jsx';
import ChatWindow from './components/ChatWindow.jsx';
import { createMessage, listMessages, listThreads, markMessageRead } from './api.js';
import useThreadSocket from './hooks/useThreadSocket.js';

const STORAGE_KEYS = {
  baseUrl: 'messagingBaseUrl',
  token: 'messagingToken'
};

function getInitialValue(key, fallback = '') {
  if (typeof window === 'undefined') {
    return fallback;
  }
  return window.localStorage.getItem(key) || fallback;
}

function decodeJwt(token) {
  if (!token) {
    return null;
  }
  const parts = token.split('.');
  if (parts.length < 2) {
    return null;
  }
  try {
    const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
    return payload;
  } catch (error) {
    return null;
  }
}

export default function App() {
  const [baseUrl, setBaseUrl] = useState(() => getInitialValue(STORAGE_KEYS.baseUrl, 'http://localhost:8000'));
  const [token, setToken] = useState(() => getInitialValue(STORAGE_KEYS.token, ''));
  const [threads, setThreads] = useState([]);
  const [selectedThread, setSelectedThread] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loadingThreads, setLoadingThreads] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [error, setError] = useState(null);
  const [currentUserId, setCurrentUserId] = useState(null);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(STORAGE_KEYS.baseUrl, baseUrl);
    }
  }, [baseUrl]);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(STORAGE_KEYS.token, token);
    }
    const payload = decodeJwt(token);
    if (payload?.user_id) {
      setCurrentUserId(payload.user_id);
    } else {
      setCurrentUserId(null);
    }
  }, [token]);

  const resetState = useCallback(() => {
    setThreads([]);
    setSelectedThread(null);
    setMessages([]);
  }, []);

  const loadThreads = useCallback(async () => {
    if (!baseUrl || !token) {
      resetState();
      return;
    }
    setLoadingThreads(true);
    setError(null);
    try {
      const data = await listThreads(baseUrl, token);
      const list = data.results || [];
      setThreads(list);
      setSelectedThread((current) => {
        if (!current) {
          return null;
        }
        return list.find((item) => item.id === current.id) || null;
      });
    } catch (err) {
      setError(err.message);
      setThreads([]);
    } finally {
      setLoadingThreads(false);
    }
  }, [baseUrl, token, resetState]);

  const loadMessages = useCallback(async (thread) => {
    if (!thread || !baseUrl || !token) {
      setMessages([]);
      setLoadingMessages(false);
      return;
    }
    setLoadingMessages(true);
    setError(null);
    try {
      const data = await listMessages(baseUrl, token, thread.id);
      const sorted = [...(data.results || [])].sort(
        (left, right) => new Date(left.created_at) - new Date(right.created_at)
      );
      setMessages(sorted);
    } catch (err) {
      setError(err.message);
      setMessages([]);
    } finally {
      setLoadingMessages(false);
    }
  }, [baseUrl, token]);

  useEffect(() => {
    if (token && baseUrl) {
      loadThreads();
    } else {
      resetState();
    }
  }, [token, baseUrl, loadThreads, resetState]);

  useEffect(() => {
    if (selectedThread) {
      loadMessages(selectedThread);
    }
  }, [selectedThread, loadMessages]);

  const handleIncomingMessage = useCallback((payload) => {
    if (!payload || !payload.id) {
      return;
    }
    setMessages((prev) => {
      const exists = prev.some((item) => item.id === payload.id);
      if (exists) {
        return prev.map((item) => (item.id === payload.id ? payload : item));
      }
      return [...prev, payload].sort((left, right) => new Date(left.created_at) - new Date(right.created_at));
    });
    setThreads((prev) =>
      prev.map((thread) =>
        thread.id === payload.thread
          ? { ...thread, last_message: payload, last_message_at: payload.created_at }
          : thread
      )
    );
    if (payload.sender !== currentUserId) {
      markMessageRead(baseUrl, token, payload.id).catch(() => {
        // ignore read errors in playground
      });
    }
  }, [baseUrl, token, currentUserId]);

  const { sendMessage, status: socketStatus } = useThreadSocket({
    baseUrl,
    threadId: selectedThread?.id,
    token,
    onMessage: handleIncomingMessage
  });

  const handleSendMessage = useCallback(async ({ content, attachment }) => {
    if (!selectedThread || !token || !baseUrl) {
      return;
    }
    if (!content && !attachment) {
      return;
    }
    if (attachment) {
      try {
        const message = await createMessage(baseUrl, token, selectedThread.id, { content, attachment });
        setMessages((prev) => [...prev, message].sort((left, right) => new Date(left.created_at) - new Date(right.created_at)));
        setThreads((prev) =>
          prev.map((thread) =>
            thread.id === message.thread
              ? { ...thread, last_message: message, last_message_at: message.created_at }
              : thread
          )
        );
      } catch (err) {
        setError(err.message);
      }
      return;
    }
    const sent = sendMessage({ content });
    if (!sent) {
      try {
        const message = await createMessage(baseUrl, token, selectedThread.id, { content });
        setMessages((prev) => [...prev, message].sort((left, right) => new Date(left.created_at) - new Date(right.created_at)));
        setThreads((prev) =>
          prev.map((thread) =>
            thread.id === message.thread
              ? { ...thread, last_message: message, last_message_at: message.created_at }
              : thread
          )
        );
      } catch (err) {
        setError(err.message);
      }
    }
  }, [selectedThread, token, baseUrl, sendMessage]);

  const toolbar = useMemo(() => (
    <div className="toolbar">
      <label htmlFor="api-base">
        API base URL
        <input
          id="api-base"
          placeholder="http://localhost:8000"
          value={baseUrl}
          onChange={(event) => setBaseUrl(event.target.value)}
        />
      </label>
      <label htmlFor="token-input">
        JWT access token
        <input
          id="token-input"
          placeholder="Paste a SimpleJWT access token"
          value={token}
          onChange={(event) => setToken(event.target.value)}
        />
      </label>
      <button type="button" onClick={loadThreads} disabled={loadingThreads}>
        {loadingThreads ? 'Loading…' : 'Load threads'}
      </button>
      {currentUserId ? <span>Detected user id: {currentUserId}</span> : <span>Unable to decode user id from token.</span>}
      {error ? <span style={{ color: '#ef4444' }}>{error}</span> : null}
    </div>
  ), [baseUrl, token, loadThreads, loadingThreads, currentUserId, error]);

  return (
    <div className="app-shell">
      <div>
        {toolbar}
        <ThreadList
          threads={threads}
          selectedThreadId={selectedThread?.id}
          onSelect={setSelectedThread}
          loading={loadingThreads}
          onRefresh={loadThreads}
        />
      </div>
      <ChatWindow
        thread={selectedThread}
        messages={messages}
        socketStatus={socketStatus}
        onSendMessage={handleSendMessage}
        currentUserId={currentUserId}
        loading={loadingMessages}
      />
    </div>
  );
}
