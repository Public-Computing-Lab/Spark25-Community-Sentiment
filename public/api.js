const runtimeBaseUrl =
  window.APP_CONFIG?.apiBaseUrl ||
  window.APP_CONFIG?.API_BASE_URL ||
  (window.location.port === '8000' ? 'http://127.0.0.1:8888' : '');

function parseTimeoutMs(value, fallback) {
  if (value === null || value === 'null' || value === 'none' || value === 'off') {
    return null;
  }
  if (value === undefined || value === '') {
    return fallback;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return fallback;
  }
  return parsed;
}

const ApiConfig = {
  baseUrl: runtimeBaseUrl,
  timeoutMs: parseTimeoutMs(
    window.APP_CONFIG?.requestTimeoutMs ?? window.APP_CONFIG?.REQUEST_TIMEOUT_MS,
    30000
  ),
  chatTimeoutMs: parseTimeoutMs(
    window.APP_CONFIG?.chatTimeoutMs ?? window.APP_CONFIG?.CHAT_TIMEOUT_MS,
    null
  ),
};

function getCookie(name) {
  const encoded = `${name}=`;
  const parts = document.cookie.split(';');
  for (const part of parts) {
    const trimmed = part.trim();
    if (trimmed.startsWith(encoded)) {
      return decodeURIComponent(trimmed.slice(encoded.length));
    }
  }
  return '';
}

async function apiRequest(path, options = {}) {
  const { timeoutMs: requestTimeoutMs, ...fetchOptions } = options;
  const timeoutMs = requestTimeoutMs === undefined ? ApiConfig.timeoutMs : requestTimeoutMs;
  const controller = new AbortController();
  const shouldAbort = Number.isFinite(timeoutMs) && timeoutMs > 0;
  const timeoutId = shouldAbort ? setTimeout(() => controller.abort(), timeoutMs) : null;
  const method = (fetchOptions.method || 'GET').toUpperCase();
  const headers = {
    ...(fetchOptions.headers || {}),
  };

  if (!headers['Content-Type'] && !['GET', 'HEAD'].includes(method)) {
    headers['Content-Type'] = 'application/json';
  }

  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrfToken = getCookie('otp_csrf');
    if (csrfToken) {
      headers['X-CSRF-Token'] = csrfToken;
    }
  }

  try {
    const response = await fetch(`${ApiConfig.baseUrl}${path}`, {
      credentials: 'include',
      signal: shouldAbort ? controller.signal : undefined,
      ...fetchOptions,
      method,
      headers,
    });

    let payload = null;
    const text = await response.text();
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch (error) {
        payload = { raw: text };
      }
    }

    if (!response.ok) {
      return {
        success: false,
        status: response.status,
        data: payload,
        error: (payload && (payload.error || payload.message)) || `Request failed with status ${response.status}`,
      };
    }

    return {
      success: true,
      status: response.status,
      data: payload,
      error: null,
    };
  } catch (error) {
    const message = error.name === 'AbortError'
      ? 'The request took too long. Please try again.'
      : (error.message || 'Unable to reach the server.');
    return {
      success: false,
      status: null,
      data: null,
      error: message,
    };
  } finally {
    if (timeoutId) {
      clearTimeout(timeoutId);
    }
  }
}

function googleAuthUrl(intent = 'login', nextPath = '/') {
  const params = new URLSearchParams({ intent, next: nextPath });
  return `${ApiConfig.baseUrl}/auth/google/start?${params.toString()}`;
}

window.ApiClient = {
  config: ApiConfig,
  request: apiRequest,
  health: () => apiRequest('/health', { method: 'GET' }),
  getSession: () => apiRequest('/auth/me', { method: 'GET' }),
  signup: (payload) => apiRequest('/auth/signup', { method: 'POST', body: JSON.stringify(payload) }),
  login: (payload) => apiRequest('/auth/login', { method: 'POST', body: JSON.stringify(payload) }),
  logout: () => apiRequest('/auth/logout', { method: 'POST', body: JSON.stringify({}) }),
  googleAuthUrl,
  completeProfile: (payload) => apiRequest('/auth/complete-profile', { method: 'POST', body: JSON.stringify(payload) }),
  unlinkGoogle: () => apiRequest('/auth/unlink/google', { method: 'POST', body: JSON.stringify({}) }),
  fetchThreads: () => apiRequest('/conversations', { method: 'GET' }),
  createThread: (payload = {}) => apiRequest('/conversations', { method: 'POST', body: JSON.stringify(payload) }),
  updateThread: (threadId, payload) => apiRequest(`/conversations/${threadId}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteThread: (threadId) => apiRequest(`/conversations/${threadId}`, { method: 'DELETE', body: JSON.stringify({}) }),
  fetchMessages: (threadId, params = {}) => {
    const qs = new URLSearchParams();
    if (params.limit) qs.set('limit', String(params.limit));
    if (params.before) qs.set('before', params.before);
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return apiRequest(`/conversations/${threadId}/messages${suffix}`, { method: 'GET' });
  },
  sendMessage: (threadId, payload) => apiRequest(`/conversations/${threadId}/messages`, {
    method: 'POST',
    body: JSON.stringify(payload),
    timeoutMs: ApiConfig.chatTimeoutMs,
  }),
  fetchEvents: (daysAhead = 14, limit = 10) => {
    const qs = new URLSearchParams({ days_ahead: String(daysAhead), limit: String(limit) });
    return apiRequest(`/events?${qs.toString()}`, { method: 'GET' });
  },
  flagInteraction: (logId, flagReason, flagDetails) => apiRequest('/log', {
    method: 'PUT',
    body: JSON.stringify({ log_id: logId, flag_reason: flagReason, flag_details: flagDetails }),
  }),
  adminStats: () => apiRequest('/admin/stats', { method: 'GET' }),
  adminFlags: () => apiRequest('/admin/flags', { method: 'GET' }),
  adminInteractions: () => apiRequest('/admin/interactions', { method: 'GET' }),
  adminNoResults: () => apiRequest('/admin/no-results', { method: 'GET' }),
  adminCommentFlag: (flagId, comment, resolved) => apiRequest(`/admin/flags/${flagId}/comment`, {
    method: 'PUT',
    body: JSON.stringify({ moderator_comment: comment, resolved }),
  }),
  adminAddKnowledge: (payload) => apiRequest('/admin/knowledge', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  adminGetKnowledge: () => apiRequest('/admin/knowledge', { method: 'GET' }),
  adminDeleteKnowledge: (id) => apiRequest(`/admin/knowledge/${id}`, { method: 'DELETE' }),
  submitCommunityNote: (content, category) => apiRequest('/community/notes', {
    method: 'POST',
    body: JSON.stringify({ content, category }),
  }),
  communityNotesChat: (messages) => apiRequest('/community/notes/chat', {
    method: 'POST',
    body: JSON.stringify({ messages }),
    timeoutMs: null,
  }),
adminGetPending: () => apiRequest('/admin/knowledge/pending', { method: 'GET' }),
adminApproveNote: (id) => apiRequest(`/admin/knowledge/${id}/approve`, {
  method: 'PUT',
  body: JSON.stringify({}),
}),
};
