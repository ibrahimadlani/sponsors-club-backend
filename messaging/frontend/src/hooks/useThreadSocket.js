import { useCallback, useEffect, useRef, useState } from 'react';

function buildWebSocketUrl(baseUrl, threadId, token) {
  const base = new URL(baseUrl);
  const protocol = base.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = new URL(`/ws/threads/${threadId}/`, `${protocol}//${base.host}`);
  url.searchParams.set('token', token);
  return url.toString();
}

export default function useThreadSocket({ baseUrl, threadId, token, onMessage }) {
  const [status, setStatus] = useState('idle');
  const socketRef = useRef(null);
  const reconnectTimer = useRef(null);

  const cleanup = useCallback(() => {
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
    if (socketRef.current) {
      socketRef.current.close(1000);
      socketRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!baseUrl || !threadId || !token) {
      cleanup();
      setStatus('idle');
      return undefined;
    }

    let isMounted = true;
    setStatus('connecting');

    try {
      const wsUrl = buildWebSocketUrl(baseUrl, threadId, token);
      const socket = new WebSocket(wsUrl);
      socketRef.current = socket;

      socket.onopen = () => {
        if (!isMounted) {
          return;
        }
        setStatus('connected');
      };

      socket.onmessage = (event) => {
        if (!isMounted) {
          return;
        }
        try {
          const payload = JSON.parse(event.data);
          if (onMessage) {
            onMessage(payload);
          }
        } catch (error) {
          // ignore malformed payloads
        }
      };

      socket.onerror = () => {
        if (!isMounted) {
          return;
        }
        setStatus('error');
      };

      socket.onclose = () => {
        if (!isMounted) {
          return;
        }
        setStatus('closed');
        reconnectTimer.current = setTimeout(() => {
          if (isMounted) {
            setStatus('reconnecting');
          }
        }, 1000);
      };
    } catch (error) {
      setStatus('error');
    }

    return () => {
      isMounted = false;
      cleanup();
    };
  }, [baseUrl, threadId, token, onMessage, cleanup]);

  const sendMessage = useCallback((payload) => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return false;
    }
    socket.send(JSON.stringify(payload));
    return true;
  }, []);

  return { sendMessage, status };
}
