const DEFAULT_API_BASE_URL = 'http://localhost:8000/api';

const normaliseBaseUrl = (value) => {
  if (!value) {
    return DEFAULT_API_BASE_URL;
  }
  return value.endsWith('/') ? value.slice(0, -1) : value;
};

export const API_BASE_URL = normaliseBaseUrl(
  process.env.NEXT_PUBLIC_API_BASE_URL,
);

export const AUTH_STORAGE_KEY = 'sponsorsclub.authTokens';

const humaniseKey = (key) => {
  if (!key) return '';
  if (key === 'non_field_errors') {
    return '';
  }
  return key.replace(/_/g, ' ');
};

export function extractErrorMessage(error, fallback = 'Une erreur inattendue est survenue.') {
  if (!error) return fallback;
  const { data } = error;
  if (typeof data === 'string' && data.trim()) {
    return data;
  }
  if (data && typeof data === 'object') {
    if (data.detail) {
      return Array.isArray(data.detail) ? data.detail.join(' ') : String(data.detail);
    }
    const messages = [];
    Object.entries(data).forEach(([key, value]) => {
      if (value == null) {
        return;
      }
      const label = humaniseKey(key);
      const prefix = label ? `${label}: ` : '';
      if (Array.isArray(value)) {
        messages.push(`${prefix}${value.join(' ')}`.trim());
      } else if (typeof value === 'string') {
        messages.push(`${prefix}${value}`.trim());
      } else {
        messages.push(`${prefix}${JSON.stringify(value)}`.trim());
      }
    });
    if (messages.length > 0) {
      return messages.join(' ');
    }
  }
  if (error.message) {
    return error.message;
  }
  return fallback;
}

export const isBrowser = () => typeof window !== 'undefined';

export async function apiRequest(path, options = {}) {
  const { method = 'GET', body, headers = {}, token, ...rest } = options;
  const resolvedPath = path.startsWith('/') ? path : `/${path}`;
  const url = `${API_BASE_URL}${resolvedPath}`;

  const requestInit = {
    method,
    headers: {
      Accept: 'application/json',
      ...headers,
    },
    ...rest,
  };

  if (token) {
    requestInit.headers.Authorization = `Bearer ${token}`;
  }

  if (body !== undefined) {
    const isBlob = typeof Blob !== 'undefined' && body instanceof Blob;
    if (body instanceof FormData || isBlob) {
      requestInit.body = body;
    } else if (typeof body === 'string') {
      requestInit.body = body;
      if (!requestInit.headers['Content-Type']) {
        requestInit.headers['Content-Type'] = 'application/json';
      }
    } else {
      requestInit.body = JSON.stringify(body);
      requestInit.headers['Content-Type'] = 'application/json';
    }
  }

  let response;
  try {
    response = await fetch(url, requestInit);
  } catch (fetchError) {
    const networkError = new Error('Impossible de contacter le serveur.');
    networkError.data = { detail: fetchError.message };
    throw networkError;
  }

  const contentType = response.headers.get('content-type');
  const isJson = contentType && contentType.includes('application/json');
  const payload = isJson ? await response.json() : await response.text();

  if (!response.ok) {
    const apiError = new Error('La requête a échoué.');
    apiError.status = response.status;
    apiError.data = payload;
    throw apiError;
  }

  return payload;
}

export function storeTokens(payload) {
  if (!isBrowser() || !payload) return;
  try {
    const record = {
      tokens: payload,
      storedAt: new Date().toISOString(),
    };
    window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(record));
  } catch (error) {
    // Fallback silently if storage is unavailable (e.g. Safari private mode).
    console.warn('Unable to persist auth tokens', error); // eslint-disable-line no-console
  }
}

export function getStoredTokens() {
  if (!isBrowser()) return null;
  try {
    const raw = window.localStorage.getItem(AUTH_STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch (error) {
    console.warn('Unable to read auth tokens', error); // eslint-disable-line no-console
    return null;
  }
}

export function clearStoredTokens() {
  if (!isBrowser()) return;
  try {
    window.localStorage.removeItem(AUTH_STORAGE_KEY);
  } catch (error) {
    console.warn('Unable to clear auth tokens', error); // eslint-disable-line no-console
  }
}
