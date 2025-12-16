// =============================================================================
// Configuration
// =============================================================================
const API_BASE_URL = 'http://127.0.0.1:8888';
// API Authentication Key
// IMPORTANT: This must match one of the keys in RETHINKAI_API_KEYS in your backend .env
const API_KEY = 'banana';

// Conversation history for context
let conversationHistory = [];

// =============================================================================
// DOM Elements
// =============================================================================
const elements = {
    // Navigation
    navItems: document.querySelectorAll('.nav-item'),
    views: document.querySelectorAll('.view'),
    
    // API Status
    apiStatus: document.getElementById('api-status'),
    
    // Chat
    chatMessages: document.getElementById('chat-messages'),
    chatForm: document.getElementById('chat-form'),
    chatInput: document.getElementById('chat-input'),
    sendBtn: document.getElementById('send-btn'),
    hintChips: document.querySelectorAll('.hint-chip'),
    
    // Events
    eventsGrid: document.getElementById('events-grid'),
    daysAhead: document.getElementById('days-ahead'),
    eventLimit: document.getElementById('event-limit'),
    refreshEvents: document.getElementById('refresh-events'),
    
    // API Tester
    endpointSelect: document.getElementById('endpoint-select'),
    requestBodyContainer: document.getElementById('request-body-container'),
    requestBody: document.getElementById('request-body'),
    queryParamsContainer: document.getElementById('query-params-container'),
    paramLimit: document.getElementById('param-limit'),
    paramDays: document.getElementById('param-days'),
    sendRequest: document.getElementById('send-request'),
    responseStatus: document.getElementById('response-status'),
    responseBody: document.getElementById('response-body'),
};

// =============================================================================
// Navigation
// =============================================================================
function initNavigation() {
    elements.navItems.forEach(item => {
        item.addEventListener('click', () => {
            const viewId = item.dataset.view;
            
            // Update nav items
            elements.navItems.forEach(nav => nav.classList.remove('active'));
            item.classList.add('active');
            
            // Update views
            elements.views.forEach(view => view.classList.remove('active'));
            document.getElementById(`${viewId}-view`).classList.add('active');
            
            // Load data for specific views
            if (viewId === 'events') {
                loadEvents();
            }
        });
    });
}

// =============================================================================
// API Status Check
// =============================================================================
async function checkApiStatus() {
    try {
        const response = await fetch(`${API_BASE_URL}/health`, {
            headers: {
                'RethinkAI-API-Key': API_KEY,
            },
        });
        const data = await response.json();
        
        if (data.status === 'ok') {
            elements.apiStatus.className = 'api-status connected';
            elements.apiStatus.querySelector('.status-text').textContent = 'API Connected';
        } else {
            elements.apiStatus.className = 'api-status disconnected';
            elements.apiStatus.querySelector('.status-text').textContent = 'API Degraded';
        }
    } catch (error) {
        elements.apiStatus.className = 'api-status disconnected';
        elements.apiStatus.querySelector('.status-text').textContent = 'API Offline';
    }
}

// =============================================================================
// Chat Functions
// =============================================================================
function addMessage(content, type = 'assistant', sources = [], mode = '') {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;
    
    const avatar = type === 'user' ? '👤' : '🤖';
    
    let sourcesHtml = '';
    if (sources && sources.length > 0) {
        const sourceTags = sources.map(s => {
            if (s.type === 'sql') {
                return `<span class="source-tag">📊 ${s.table}</span>`;
            } else {
                return `<span class="source-tag">📄 ${s.source}</span>`;
            }
        }).join('');
        sourcesHtml = `<div class="message-sources">Sources: ${sourceTags}</div>`;
    }
    
    let modeHtml = '';
    if (mode) {
        modeHtml = `<div class="message-mode">Mode: ${mode}</div>`;
    }
    
    // Convert markdown-like formatting
    let formattedContent = content
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br>');
    
    messageDiv.innerHTML = `
        <div class="message-avatar">${avatar}</div>
        <div class="message-content">
            <p>${formattedContent}</p>
            ${sourcesHtml}
            ${modeHtml}
        </div>
    `;
    
    elements.chatMessages.appendChild(messageDiv);
    elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
}

function addTypingIndicator() {
    const indicator = document.createElement('div');
    indicator.className = 'message assistant';
    indicator.id = 'typing-indicator';
    indicator.innerHTML = `
        <div class="message-avatar">🤖</div>
        <div class="message-content">
            <div class="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
            </div>
        </div>
    `;
    elements.chatMessages.appendChild(indicator);
    elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
}

function removeTypingIndicator() {
    const indicator = document.getElementById('typing-indicator');
    if (indicator) {
        indicator.remove();
    }
}

async function sendChatMessage(message) {
    // Add user message to UI
    addMessage(message, 'user');
    
    // Add to conversation history
    conversationHistory.push({ role: 'user', content: message });
    
    // Show typing indicator
    addTypingIndicator();
    
    // Disable input
    elements.chatInput.disabled = true;
    elements.sendBtn.disabled = true;
    
    try {
        const response = await fetch(`${API_BASE_URL}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'RethinkAI-API-Key': API_KEY,
            },
            body: JSON.stringify({
                message: message,
                conversation_history: conversationHistory.slice(-10), // Last 10 messages
            }),
        });
        
        const data = await response.json();
        
        removeTypingIndicator();
        
        if (response.ok) {
            // Add assistant response to UI
            addMessage(data.response, 'assistant', data.sources, data.mode);
            
            // Add to conversation history
            conversationHistory.push({ role: 'assistant', content: data.response });
        } else {
            addMessage(`Error: ${data.error || 'Something went wrong'}`, 'assistant');
        }
    } catch (error) {
        removeTypingIndicator();
        addMessage(`Error: Could not connect to the API. Make sure the server is running.`, 'assistant');
    } finally {
        // Re-enable input
        elements.chatInput.disabled = false;
        elements.sendBtn.disabled = false;
        elements.chatInput.focus();
    }
}

function initChat() {
    // Form submission
    elements.chatForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const message = elements.chatInput.value.trim();
        if (message) {
            elements.chatInput.value = '';
            sendChatMessage(message);
        }
    });
    
    // Hint chips
    elements.hintChips.forEach(chip => {
        chip.addEventListener('click', () => {
            const query = chip.dataset.query;
            elements.chatInput.value = query;
            elements.chatInput.focus();
        });
    });
}

// =============================================================================
// Events Functions
// =============================================================================
async function loadEvents() {
    const daysAhead = elements.daysAhead.value;
    const limit = elements.eventLimit.value;
    
    elements.eventsGrid.innerHTML = '<div class="loading-state">Loading events...</div>';
    
    try {
        const response = await fetch(`${API_BASE_URL}/events?days_ahead=${daysAhead}&limit=${limit}`, {
            headers: {
                'RethinkAI-API-Key': API_KEY,
            },
        });
        const data = await response.json();
        
        if (response.ok && data.events && data.events.length > 0) {
            elements.eventsGrid.innerHTML = data.events.map(event => `
                <div class="event-card">
                    <div class="event-date-badge">${event.event_date || event.start_date}</div>
                    <h3>${event.event_name}</h3>
                    ${event.start_time ? `<div class="event-time">🕐 ${formatTime(event.start_time)}${event.end_time ? ' - ' + formatTime(event.end_time) : ''}</div>` : ''}
                    <p class="event-description">${event.description || 'No description available'}</p>
                </div>
            `).join('');
        } else if (data.events && data.events.length === 0) {
            elements.eventsGrid.innerHTML = '<div class="empty-state">No upcoming events found</div>';
        } else {
            elements.eventsGrid.innerHTML = `<div class="empty-state">Error: ${data.error || 'Failed to load events'}</div>`;
        }
    } catch (error) {
        elements.eventsGrid.innerHTML = '<div class="empty-state">Could not connect to API</div>';
    }
}

function formatTime(timeStr) {
    if (!timeStr) return '';
    const [hours, minutes] = timeStr.split(':');
    const h = parseInt(hours);
    const ampm = h >= 12 ? 'PM' : 'AM';
    const h12 = h % 12 || 12;
    return `${h12}:${minutes} ${ampm}`;
}

function initEvents() {
    elements.refreshEvents.addEventListener('click', loadEvents);
    elements.daysAhead.addEventListener('change', loadEvents);
    elements.eventLimit.addEventListener('change', loadEvents);
}

// =============================================================================
// API Tester Functions
// =============================================================================
function updateApiTesterUI() {
    const endpoint = elements.endpointSelect.value;
    
    // Show/hide appropriate inputs
    const needsBody = ['chat', 'log-post', 'log-put'].includes(endpoint);
    const needsParams = endpoint === 'events';
    
    elements.requestBodyContainer.style.display = needsBody ? 'block' : 'none';
    elements.queryParamsContainer.style.display = needsParams ? 'block' : 'none';
    
    // Set default request body
    const defaults = {
        'chat': JSON.stringify({ message: "What events are happening this week?", conversation_history: [] }, null, 2),
        'log-post': JSON.stringify({ client_query: "test question", app_response: "test answer", mode: "test" }, null, 2),
        'log-put': JSON.stringify({ log_id: 1, client_response_rating: "helpful" }, null, 2),
    };
    
    if (defaults[endpoint]) {
        elements.requestBody.value = defaults[endpoint];
    }
}

async function sendApiRequest() {
    const endpoint = elements.endpointSelect.value;
    let url = API_BASE_URL;
    let options = {
        headers: {
            'Content-Type': 'application/json',
            'RethinkAI-API-Key': API_KEY,
        },
    };
    
    // Build request based on endpoint
    switch (endpoint) {
        case 'health':
            url += '/health';
            options.method = 'GET';
            break;
        case 'events':
            const limit = elements.paramLimit.value || '10';
            const days = elements.paramDays.value || '7';
            url += `/events?limit=${limit}&days_ahead=${days}`;
            options.method = 'GET';
            break;
        case 'chat':
            url += '/chat';
            options.method = 'POST';
            options.body = elements.requestBody.value;
            break;
        case 'log-post':
            url += '/log';
            options.method = 'POST';
            options.body = elements.requestBody.value;
            break;
        case 'log-put':
            url += '/log';
            options.method = 'PUT';
            options.body = elements.requestBody.value;
            break;
    }
    
    elements.responseBody.textContent = 'Loading...';
    elements.responseStatus.textContent = '';
    elements.responseStatus.className = 'response-status';
    
    try {
        const startTime = Date.now();
        const response = await fetch(url, options);
        const elapsed = Date.now() - startTime;
        
        const data = await response.json();
        
        elements.responseStatus.textContent = `${response.status} ${response.statusText} (${elapsed}ms)`;
        elements.responseStatus.className = `response-status ${response.ok ? 'success' : 'error'}`;
        elements.responseBody.textContent = JSON.stringify(data, null, 2);
    } catch (error) {
        elements.responseStatus.textContent = 'Error';
        elements.responseStatus.className = 'response-status error';
        elements.responseBody.textContent = `Failed to connect: ${error.message}`;
    }
}

function initApiTester() {
    elements.endpointSelect.addEventListener('change', updateApiTesterUI);
    elements.sendRequest.addEventListener('click', sendApiRequest);
    updateApiTesterUI();
}

// =============================================================================
// Initialize
// =============================================================================
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initChat();
    initEvents();
    initApiTester();
    
    // Check API status on load and periodically
    checkApiStatus();
    setInterval(checkApiStatus, 30000); // Check every 30 seconds
});

