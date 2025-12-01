// Main Application Logic for Dorchester Community Assistant

// Configuration
const API_BASE_URL = 'http://127.0.0.1:8888';

// Application State
const state = {
  conversationHistory: [],
  isSendingMessage: false,
  isLoadingEvents: false,
  sidebarOpen: false,
};

// DOM Elements
const elements = {
  // Chat
  chatMessages: document.getElementById('chat-messages'),
  chatForm: document.getElementById('chat-form'),
  chatInput: document.getElementById('chat-input'),
  chatSubmit: document.getElementById('chat-submit'),
  chatError: document.getElementById('chat-error'),
  suggestions: document.getElementById('suggestions'),
  
  // Events
  sidebar: document.getElementById('sidebar'),
  eventsList: document.getElementById('events-list'),
  eventsLoading: document.getElementById('events-loading'),
  eventsError: document.getElementById('events-error'),
  eventsEmpty: document.getElementById('events-empty'),
  eventsDays: document.getElementById('events-days'),
  eventsLimit: document.getElementById('events-limit'),
  eventsRefresh: document.getElementById('events-refresh'),
  
  // Status
  apiStatus: document.getElementById('api-status'),
};

// ============================================================================
// Utility Functions
// ============================================================================

function showError(element, message) {
  if (!element) return;
  if (message) {
    element.textContent = message;
    element.hidden = false;
  } else {
    element.hidden = true;
    element.textContent = '';
  }
}

function formatTime(timeStr) {
  if (!timeStr) return '';
  const [hours, minutes] = String(timeStr).split(':');
  const h = parseInt(hours, 10);
  if (isNaN(h)) return timeStr;
  const ampm = h >= 12 ? 'PM' : 'AM';
  const h12 = h % 12 || 12;
  return `${h12}:${minutes || '00'} ${ampm}`;
}

// Map SQL table names to user-friendly source descriptions
const sourceMapping = {
  'bos311_data': '311 Service Requests from https://data.boston.gov/',
  'shots_fired_data': 'Crime data from https://data.boston.gov/',
  'homicide_data': 'Crime data from https://data.boston.gov/',
  'weekly_events': 'Community newsletters',
  'events': 'Community newsletters',
  'crime': 'Crime data from https://data.boston.gov/',
  'crime_incident': 'Crime data from https://data.boston.gov/',
};

function formatSource(source) {
  if (source.type === 'sql' && source.table) {
    const tableName = source.table.toLowerCase();
    // Check if we have a mapping for this table
    if (sourceMapping[tableName]) {
      return sourceMapping[tableName];
    }
    // Check for partial matches (e.g., table names with prefixes)
    for (const [key, value] of Object.entries(sourceMapping)) {
      if (tableName.includes(key) || key.includes(tableName)) {
        return value;
      }
    }
    // Check for common patterns
    if (tableName.includes('crime') || tableName.includes('911') || tableName.includes('shot')) {
      return 'Crime data from https://data.boston.gov/';
    }
    if (tableName.includes('311') || tableName.includes('service')) {
      return '311 Service Requests from https://data.boston.gov/';
    }
    if (tableName.includes('event') || tableName.includes('newsletter') || tableName.includes('weekly')) {
      return 'Community newsletters';
    }
    // Default fallback for SQL tables
    return `City data from https://data.boston.gov/`;
  } else if (source.type === 'rag' && source.source) {
    const sourceName = source.source.toLowerCase();
    // Check if it's an event-related source
    if (sourceName.includes('event') || sourceName.includes('newsletter') || sourceName.includes('weekly')) {
      return 'Community newsletters';
    }
    // For other RAG sources, use the source name or a friendly description
    return source.source || 'Community documents';
  }
  return 'Community data';
}

// ============================================================================
// API Status
// ============================================================================

async function updateApiStatus() {
  if (!elements.apiStatus) return;
  
  const dot = elements.apiStatus.querySelector('.status-dot');
  const text = elements.apiStatus.querySelector('.status-text');
  
  try {
    const response = await fetch(`${API_BASE_URL}/health`);
    const data = await response.json();
    
    elements.apiStatus.className = 'status-indicator';
    
    if (data.status === 'ok') {
      elements.apiStatus.classList.add('connected');
      if (text) text.textContent = 'Connected';
    } else {
      elements.apiStatus.classList.add('error');
      if (text) text.textContent = 'Degraded';
    }
  } catch (error) {
    elements.apiStatus.className = 'status-indicator error';
    if (text) text.textContent = 'Offline';
  }
}

// ============================================================================
// Chat Functions
// ============================================================================

function addMessage({ text, type, sources, mode, isTyping }) {
  if (!elements.chatMessages) return null;
  
  const messageEl = document.createElement('div');
  messageEl.className = `message ${type}`;
  
  // Avatar
  const avatar = document.createElement('div');
  avatar.className = 'message-avatar';
  avatar.textContent = type === 'user' ? '👤' : '🤖';
  
  // Content
  const content = document.createElement('div');
  content.className = 'message-content';
  
  if (isTyping) {
    const typingDiv = document.createElement('div');
    typingDiv.className = 'typing-indicator';
    typingDiv.innerHTML = '<span></span><span></span><span></span>';
    content.appendChild(typingDiv);
  } else {
    const textDiv = document.createElement('div');
    textDiv.className = 'message-text';
    
    // Basic markdown formatting
    let formatted = String(text || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\n/g, '<br>');
    
    // Wrap in paragraphs
    const paragraphs = formatted.split('<br>');
    paragraphs.forEach((para, i) => {
      if (para.trim()) {
        const p = document.createElement('p');
        p.innerHTML = para;
        textDiv.appendChild(p);
      }
    });
    
    content.appendChild(textDiv);
    
    // Sources - display in user-friendly way
    if (Array.isArray(sources) && sources.length > 0) {
      const meta = document.createElement('div');
      meta.className = 'message-meta';
      
      const label = document.createElement('span');
      label.className = 'meta-label';
      label.textContent = 'Sources:';
      meta.appendChild(label);
      
      // Get unique formatted sources
      const formattedSources = new Set();
      sources.forEach(source => {
        const formatted = formatSource(source);
        formattedSources.add(formatted);
      });
      
      // Create pills for each unique source
      formattedSources.forEach(formattedSource => {
        const pill = document.createElement('span');
        pill.className = 'meta-pill';
        pill.textContent = formattedSource;
        meta.appendChild(pill);
      });
      
      content.appendChild(meta);
    }
  }
  
  messageEl.appendChild(avatar);
  messageEl.appendChild(content);
  elements.chatMessages.appendChild(messageEl);
  
  // Scroll to bottom
  elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
  
  return messageEl;
}

function setChatLoading(loading) {
  state.isSendingMessage = loading;
  if (elements.chatInput) elements.chatInput.disabled = loading;
  if (elements.chatSubmit) elements.chatSubmit.disabled = loading;
}

async function handleChatSubmit(e) {
  e.preventDefault();
  if (state.isSendingMessage) return;
  
  const message = elements.chatInput?.value.trim();
  if (!message) return;
  
  showError(elements.chatError, '');
  
  // Check if this is an event query (has event ID stored)
  const eventId = elements.chatInput?.dataset.eventId;
  const eventName = elements.chatInput?.dataset.eventName;
  
  // Message to show user (clean, no technical details)
  const userMessage = message;
  
  // Message to send to backend (includes event ID for database query if present)
  let backendMessage = message;
  if (eventId && eventName) {
    // Format message to query the database for this specific event
    // The backend will query weekly_events table with this ID
    backendMessage = `Query the weekly_events database for the event "${eventName}" with ID ${eventId}. Provide complete details about this specific event without mentioning the ID number.`;
  }
  
  // Add user message (show clean version to user)
  addMessage({ text: userMessage, type: 'user' });
  // DON'T add to conversationHistory yet - we'll add it after we get the response
  
  // Clear input and event data
  if (elements.chatInput) {
    elements.chatInput.value = '';
    delete elements.chatInput.dataset.eventId;
    delete elements.chatInput.dataset.eventName;
  }
  
  // Show typing indicator
  setChatLoading(true);
  const typingEl = addMessage({ text: '', type: 'assistant', isTyping: true });
  
  try {
    const response = await fetch(`${API_BASE_URL}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        message: backendMessage.trim(),
        conversation_history: state.conversationHistory.slice(-10),
      }),
    });
    
    if (typingEl && typingEl.parentNode) {
      typingEl.remove();
    }
    
    const data = await response.json();
    
    if (response.ok) {
      const responseText = data.response || 'I could not find an answer to that.';
      const sources = data.sources || [];
      const mode = data.mode || '';
      
      addMessage({
        text: responseText,
        type: 'assistant',
        sources,
        mode: '', // Don't show mode to users
      });
      
      // NOW add both messages to conversation history after successful response
      state.conversationHistory.push({ role: 'user', content: userMessage });
      state.conversationHistory.push({ role: 'assistant', content: responseText });
    } else {
      showError(elements.chatError, data.error || 'Failed to send message. Please try again.');
    }
  } catch (error) {
    if (typingEl && typingEl.parentNode) {
      typingEl.remove();
    }
    showError(elements.chatError, 'Could not connect to the API. Make sure the server is running.');
  } finally {
    setChatLoading(false);
    if (elements.chatInput) elements.chatInput.focus();
  }
}

function initChat() {
  if (elements.chatForm) {
    elements.chatForm.addEventListener('submit', handleChatSubmit);
  }
  
  // Suggestion chips
  if (elements.suggestions) {
    elements.suggestions.addEventListener('click', (e) => {
      if (e.target.classList.contains('suggestion-chip')) {
        const query = e.target.getAttribute('data-query');
        if (query && elements.chatInput) {
          elements.chatInput.value = query;
          elements.chatInput.focus();
        }
      }
    });
  }
}

// ============================================================================
// Events Functions
// ============================================================================

function setEventsLoading(loading) {
  state.isLoadingEvents = loading;
  if (elements.eventsLoading) {
    if (loading) {
      elements.eventsLoading.hidden = false;
      elements.eventsLoading.style.display = 'flex';
    } else {
      elements.eventsLoading.hidden = true;
      elements.eventsLoading.style.display = 'none';
    }
  }
  if (elements.eventsList) {
    elements.eventsList.style.opacity = loading ? '0.5' : '1';
    elements.eventsList.style.pointerEvents = loading ? 'none' : 'auto';
  }
}

async function loadEvents() {
  if (state.isLoadingEvents) return;
  
  showError(elements.eventsError, '');
  if (elements.eventsEmpty) elements.eventsEmpty.hidden = true;
  if (elements.eventsList) elements.eventsList.innerHTML = '';
  
  const days = elements.eventsDays ? parseInt(elements.eventsDays.value) : 14;
  const limit = elements.eventsLimit ? parseInt(elements.eventsLimit.value) : 10;
  
  setEventsLoading(true);
  
  try {
    const response = await fetch(`${API_BASE_URL}/events?days_ahead=${days}&limit=${limit}`);
    const data = await response.json();
    
    if (response.ok && data.events && data.events.length > 0) {
      if (!elements.eventsList) {
        setEventsLoading(false);
        return;
      }
      
      data.events.forEach(event => {
        const card = document.createElement('div');
        card.className = 'event-card';
        
        const date = event.event_date || event.start_date || 'Upcoming';
        const startTime = formatTime(event.start_time);
        const endTime = formatTime(event.end_time);
        const timeStr = startTime && endTime 
          ? `${startTime} - ${endTime}`
          : startTime || '';
        
        card.innerHTML = `
          <div class="event-date">${date}</div>
          <h3 class="event-title">${event.event_name || 'Community Event'}</h3>
          ${timeStr ? `<p class="event-time">🕐 ${timeStr}</p>` : ''}
          <p class="event-description">${event.description || 'No description available.'}</p>
        `;
        
        // Store event data on the card element
        card.dataset.eventId = event.id;
        card.dataset.eventName = event.event_name || 'Community Event';
        card.dataset.eventDate = date;
        card.dataset.eventTime = timeStr;
        card.dataset.eventDescription = event.description || '';
        
        // Make event card clickable - send message that queries the events database
        card.addEventListener('click', () => {
          if (elements.chatInput && event.id) {
            const eventName = event.event_name || 'this event';
            
            // Show user-friendly message in the input
            const userMessage = `Tell me more about "${eventName}"`;
            elements.chatInput.value = userMessage;
            
            // Store event ID in a data attribute for the backend to use
            elements.chatInput.dataset.eventId = event.id;
            elements.chatInput.dataset.eventName = eventName;
            
            elements.chatInput.focus();
            
            // Auto-submit the message to query the database
            if (elements.chatForm && !state.isSendingMessage) {
              // Trigger form submission
              const submitEvent = new Event('submit', { cancelable: true, bubbles: true });
              elements.chatForm.dispatchEvent(submitEvent);
            }
          }
        });
        
        elements.eventsList.appendChild(card);
      });
      setEventsLoading(false);
    } else if (data.events && data.events.length === 0) {
      if (elements.eventsEmpty) elements.eventsEmpty.hidden = false;
      setEventsLoading(false);
    } else {
      showError(elements.eventsError, data.error || 'Failed to load events.');
      setEventsLoading(false);
    }
  } catch (error) {
    showError(elements.eventsError, 'Could not connect to API. Please check your connection.');
    setEventsLoading(false);
  }
}

function initEvents() {
  if (elements.eventsRefresh) {
    elements.eventsRefresh.addEventListener('click', loadEvents);
  }
  
  if (elements.eventsDays) {
    elements.eventsDays.addEventListener('change', loadEvents);
  }
  
  if (elements.eventsLimit) {
    elements.eventsLimit.addEventListener('change', loadEvents);
  }
  
  // Initial load
  loadEvents();
}

// ============================================================================
// Sidebar Functions (no longer needed - sidebar always visible)
// ============================================================================

function initSidebar() {
  // Sidebar is always visible now, no toggle functionality needed
}

// ============================================================================
// Initialization
// ============================================================================

function initApp() {
  // Check if elements exist before initializing
  if (!elements.chatMessages || !elements.chatForm) {
    console.error('Required DOM elements not found');
    return;
  }
  
  initChat();
  initEvents();
  initSidebar();
  updateApiStatus();
  
  // Update API status every 30 seconds
  setInterval(updateApiStatus, 30000);
  
  // Handle window resize
  window.addEventListener('resize', () => {
    if (window.innerWidth > 768 && state.sidebarOpen) {
      // Keep sidebar open on desktop
    } else if (window.innerWidth <= 768 && !state.sidebarOpen) {
      // Close sidebar overlay on mobile resize
      if (elements.sidebarOverlay) {
        elements.sidebarOverlay.hidden = true;
      }
    }
  });
}

// Start app when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  initApp();
}
