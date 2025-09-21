function resolveUrl(baseUrl, pathOrUrl) {
  if (!pathOrUrl) {
    throw new Error('Missing URL path');
  }
  try {
    return new URL(pathOrUrl).toString();
  } catch (error) {
    return new URL(pathOrUrl, baseUrl).toString();
  }
}

function authHeaders(token, extra = {}) {
  return {
    ...extra,
    Authorization: `Bearer ${token}`
  };
}

export async function listThreads(baseUrl, token, pageUrl) {
  const target = pageUrl ? resolveUrl(baseUrl, pageUrl) : resolveUrl(baseUrl, '/api/threads/');
  const response = await fetch(target, {
    headers: authHeaders(token)
  });
  if (!response.ok) {
    throw new Error('Failed to fetch threads');
  }
  return response.json();
}

export async function listMessages(baseUrl, token, threadId, pageUrl) {
  const target = pageUrl
    ? resolveUrl(baseUrl, pageUrl)
    : resolveUrl(baseUrl, `/api/threads/${threadId}/messages/`);
  const response = await fetch(target, {
    headers: authHeaders(token)
  });
  if (!response.ok) {
    throw new Error('Failed to fetch messages');
  }
  return response.json();
}

export async function createMessage(baseUrl, token, threadId, payload) {
  const target = resolveUrl(baseUrl, `/api/threads/${threadId}/messages/`);
  const hasAttachment = Boolean(payload.attachment);
  const body = new FormData();
  if (payload.content) {
    body.append('content', payload.content);
  }
  if (payload.attachment) {
    body.append('attachment', payload.attachment);
  }
  const options = {
    method: 'POST',
    headers: hasAttachment ? { Authorization: `Bearer ${token}` } : authHeaders(token, { 'Content-Type': 'application/json' }),
    body: hasAttachment ? body : JSON.stringify({ content: payload.content })
  };
  if (hasAttachment) {
    options.body = body;
  }
  const response = await fetch(target, options);
  if (!response.ok) {
    throw new Error('Failed to create message');
  }
  return response.json();
}

export async function markMessageRead(baseUrl, token, messageId) {
  const target = resolveUrl(baseUrl, `/api/messages/${messageId}/read/`);
  const response = await fetch(target, {
    method: 'POST',
    headers: authHeaders(token)
  });
  if (!response.ok) {
    throw new Error('Failed to mark message as read');
  }
  return response.json();
}
