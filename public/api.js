// API Client for Dorchester Community Assistant
// Handles all API communication with error handling and timeouts

const ApiConfig = {
  baseUrl: 'http://127.0.0.1:8888',
  timeoutMs: 30000,
  apiKey: 'banana', // Set your RETHINKAI_API_KEY here
};

/**
 * Make an API request with timeout and error handling
 * @param {string} path - API endpoint path
 * @param {Object} options - Fetch options
 * @returns {Promise<{success: boolean, status: number|null, data: any, error: string|null}>}
 */
async function apiRequest(path, options = {}) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), ApiConfig.timeoutMs);

  try {
    const response = await fetch(`${ApiConfig.baseUrl}${path}`, {
      headers: {
        'Content-Type': 'application/json',
        'RethinkAI-API-Key': ApiConfig.apiKey,
        ...(options.headers || {}),
      },
      credentials: 'include', // Include cookies for session management
      signal: controller.signal,
      ...options,
    });

    let payload = null;
    try {
      const text = await response.text();
      if (text) {
        payload = JSON.parse(text);
      }
    } catch (e) {
      // Not JSON or empty response
    }

    if (!response.ok) {
      const message = 
        (payload && (payload.error || payload.message)) ||
        `Request failed with status ${response.status}`;

      return {
        success: false,
        status: response.status,
        data: payload,
        error: message,
      };
    }

    return {
      success: true,
      status: response.status,
      data: payload,
      error: null,
    };
  } catch (error) {
    let message = 'Unable to reach the server. Please check your connection.';
    
    if (error.name === 'AbortError') {
      message = 'The request took too long. Please try again.';
    } else if (error.message) {
      message = error.message;
    }

    return {
      success: false,
      status: null,
      data: null,
      error: message,
    };
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * Check API health status
 * @returns {Promise<{success: boolean, status: number|null, data: any, error: string|null}>}
 */
async function checkHealth() {
  return apiRequest('/health', { method: 'GET' });
}

/**
 * Send a chat message
 * @param {string} message - User message
 * @param {Array} conversationHistory - Previous conversation messages
 * @returns {Promise<{success: boolean, status: number|null, data: any, error: string|null}>}
 */
async function sendChatMessage(message, conversationHistory = []) {
  return apiRequest('/chat', {
    method: 'POST',
    body: JSON.stringify({
      message: message.trim(),
      conversation_history: conversationHistory.slice(-10), // Last 10 messages
    }),
  });
}

/**
 * Fetch upcoming events
 * @param {number} daysAhead - Number of days to look ahead
 * @param {number} limit - Maximum number of events to return
 * @returns {Promise<{success: boolean, status: number|null, data: any, error: string|null}>}
 */
async function fetchEvents(daysAhead = 14, limit = 10) {
  const params = new URLSearchParams({
    days_ahead: String(daysAhead),
    limit: String(limit),
  });
  
  return apiRequest(`/events?${params.toString()}`, {
    method: 'GET',
  });
}

/**
 * Log an interaction (optional)
 * @param {Object} data - Log data
 * @returns {Promise<{success: boolean, status: number|null, data: any, error: string|null}>}
 */
async function logInteraction(data) {
  return apiRequest('/log', {
    method: 'POST',
    body: JSON.stringify(data || {}),
  });
}

// Export API client
window.ApiClient = {
  config: ApiConfig,
  checkHealth,
  sendChatMessage,
  fetchEvents,
  logInteraction,
};
