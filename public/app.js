const state = {
  authMode: 'login',
  theme: 'dark',
  eventsPanelCollapsed: false,
  eventsPanelWidth: 340,
  user: null,
  googleEnabled: false,
  threads: [],
  activeThreadId: null,
  messages: [],
  messageVersion: 0,
  isSendingMessage: false,
  isLoadingEvents: false,
  currentFlagLogId: null,
  threadModalMode: null,
  threadModalThreadId: null,
};

const elements = {
  authView: document.getElementById('auth-view'),
  profileView: document.getElementById('profile-view'),
  appView: document.getElementById('app-view'),
  authError: document.getElementById('auth-error'),
  profileError: document.getElementById('profile-error'),
  loginForm: document.getElementById('login-form'),
  signupForm: document.getElementById('signup-form'),
  profileForm: document.getElementById('profile-form'),
  tabLogin: document.getElementById('tab-login'),
  tabSignup: document.getElementById('tab-signup'),
  googleAuthButton: document.getElementById('google-auth-button'),
  profileLogout: document.getElementById('profile-logout'),
  accountUsername: document.getElementById('account-username'),
  accountEmail: document.getElementById('account-email'),
  accountProviders: document.getElementById('account-providers'),
  googleLinkToggle: document.getElementById('google-link-toggle'),
  adminLink: document.getElementById('admin-link'),
  logoutButton: document.getElementById('logout-button'),
  threadList: document.getElementById('thread-list'),
  newThreadButton: document.getElementById('new-thread-button'),
  activeThreadTitle: document.getElementById('active-thread-title'),
  renameThreadButton: document.getElementById('rename-thread-button'),
  deleteThreadButton: document.getElementById('delete-thread-button'),
  themeToggle: document.getElementById('theme-toggle'),
  themeToggles: Array.from(document.querySelectorAll('[data-theme-toggle]')),
  eventsPanelToggle: document.getElementById('events-panel-toggle'),
  eventsResizer: document.getElementById('events-resizer'),
  chatMessages: document.getElementById('chat-messages'),
  chatError: document.getElementById('chat-error'),
  chatForm: document.getElementById('chat-form'),
  chatInput: document.getElementById('chat-input'),
  chatSubmit: document.getElementById('chat-submit'),
  suggestions: document.getElementById('suggestions'),
  apiStatus: document.getElementById('api-status'),
  eventsList: document.getElementById('events-list'),
  eventsLoading: document.getElementById('events-loading'),
  eventsError: document.getElementById('events-error'),
  eventsEmpty: document.getElementById('events-empty'),
  eventsDays: document.getElementById('events-days'),
  eventsLimit: document.getElementById('events-limit'),
  eventsRefresh: document.getElementById('events-refresh'),
  flagModal: document.getElementById('flag-modal'),
  flagDetail: document.getElementById('flag-detail'),
  flagError: document.getElementById('flag-error'),
  flagCancel: document.getElementById('flag-cancel'),
  flagSubmit: document.getElementById('flag-submit'),
  threadModal: document.getElementById('thread-modal'),
  threadModalTitle: document.getElementById('thread-modal-title'),
  threadModalCopy: document.getElementById('thread-modal-copy'),
  threadModalField: document.getElementById('thread-modal-field'),
  threadModalInput: document.getElementById('thread-modal-input'),
  threadModalError: document.getElementById('thread-modal-error'),
  threadModalCancel: document.getElementById('thread-modal-cancel'),
  threadModalConfirm: document.getElementById('thread-modal-confirm'),
  toastStack: document.getElementById('toast-stack'),
};

const sourceMapping = {
  bos311_data: { label: '311 Service Requests', path: 'https://data.boston.gov/dataset/311-service-requests' },
  shots_fired_data: { label: 'Crime data (shots fired)', path: 'https://data.boston.gov/dataset/crime-incident-reports-august-2015-to-date-source-new-system' },
  homicide_data: { label: 'Crime data (homicides)', path: 'https://data.boston.gov/dataset/crime-incident-reports-august-2015-to-date-source-new-system' },
  weekly_events: { label: 'Community newsletters', path: null },
  crime_incident: { label: 'Crime data', path: 'https://data.boston.gov/dataset/crime-incident-reports-august-2015-to-date-source-new-system' },
};

const providerLabels = {
  password: 'Email',
  google: 'Google',
};

const THEME_STORAGE_KEY = 'otp-theme';
const EVENTS_PANEL_STORAGE_KEY = 'otp-events-panel-collapsed';
const EVENTS_PANEL_WIDTH_STORAGE_KEY = 'otp-events-panel-width';
const CHAT_INPUT_PLACEHOLDER = 'Ask about events, services, safety, or neighborhood trends...';
const DEFAULT_EVENTS_PANEL_WIDTH = 340;
const MIN_EVENTS_PANEL_WIDTH = 280;
const MAX_EVENTS_PANEL_WIDTH = 560;
const EVENT_CARD_MAX_HEIGHT = 390;

let eventsPanelResizeState = null;
let eventCardsLayoutFrame = null;
let eventCardsResizeObserver = null;

function getStoredTheme() {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return stored === 'light' ? 'light' : 'dark';
  } catch (error) {
    return 'dark';
  }
}

function applyTheme(theme) {
  state.theme = theme === 'light' ? 'light' : 'dark';
  document.body.dataset.theme = state.theme;

  const isLight = state.theme === 'light';
  const label = isLight ? 'Switch to dark mode' : 'Switch to light mode';
  elements.themeToggles.forEach((toggle) => {
    toggle.setAttribute('aria-label', label);
    toggle.setAttribute('title', label);

    const icon = toggle.querySelector('.theme-toggle-icon');
    if (icon) {
      icon.textContent = isLight ? '☾' : '☀';
    }
  });
}

function toggleTheme() {
  const nextTheme = state.theme === 'light' ? 'dark' : 'light';
  applyTheme(nextTheme);
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, nextTheme);
  } catch (error) {
    // Ignore storage failures; the toggle still works for the active session.
  }
}

function getStoredEventsPanelCollapsed() {
  try {
    return window.localStorage.getItem(EVENTS_PANEL_STORAGE_KEY) === 'true';
  } catch (error) {
    return false;
  }
}

function clampEventsPanelWidth(width) {
  const numeric = Number.parseInt(width, 10);
  if (!Number.isFinite(numeric)) {
    return DEFAULT_EVENTS_PANEL_WIDTH;
  }
  return Math.min(MAX_EVENTS_PANEL_WIDTH, Math.max(MIN_EVENTS_PANEL_WIDTH, numeric));
}

function getStoredEventsPanelWidth() {
  try {
    return clampEventsPanelWidth(window.localStorage.getItem(EVENTS_PANEL_WIDTH_STORAGE_KEY));
  } catch (error) {
    return DEFAULT_EVENTS_PANEL_WIDTH;
  }
}

function applyEventsPanelWidth(width, options = {}) {
  const { persist = false } = options;
  const nextWidth = clampEventsPanelWidth(width);
  state.eventsPanelWidth = nextWidth;
  document.body.style.setProperty('--events-panel-width', `${nextWidth}px`);
  scheduleEventCardLayoutSync();

  if (persist) {
    try {
      window.localStorage.setItem(EVENTS_PANEL_WIDTH_STORAGE_KEY, String(nextWidth));
    } catch (error) {
      // Ignore storage failures; resizing still works for the current session.
    }
  }
}

function applyEventsPanelCollapsed(collapsed) {
  state.eventsPanelCollapsed = Boolean(collapsed);
  document.body.dataset.eventsCollapsed = state.eventsPanelCollapsed ? 'true' : 'false';

  if (!elements.eventsPanelToggle) return;

  const label = state.eventsPanelCollapsed ? 'Expand events panel' : 'Collapse events panel';
  elements.eventsPanelToggle.setAttribute('aria-label', label);
  elements.eventsPanelToggle.setAttribute('title', label);
  elements.eventsPanelToggle.setAttribute('aria-pressed', String(state.eventsPanelCollapsed));
  elements.eventsPanelToggle.classList.toggle('is-collapsed', state.eventsPanelCollapsed);

  if (elements.eventsResizer) {
    elements.eventsResizer.setAttribute('aria-hidden', String(state.eventsPanelCollapsed));
    elements.eventsResizer.tabIndex = state.eventsPanelCollapsed ? -1 : 0;
  }
}

function toggleEventsPanel() {
  const nextCollapsed = !state.eventsPanelCollapsed;
  applyEventsPanelCollapsed(nextCollapsed);
  try {
    window.localStorage.setItem(EVENTS_PANEL_STORAGE_KEY, String(nextCollapsed));
  } catch (error) {
    // Ignore storage failures; collapse still works for the current session.
  }
}

function beginEventsPanelResize(event) {
  if (state.eventsPanelCollapsed) return;
  if (window.matchMedia('(max-width: 1024px)').matches) return;
  if (event.button !== 0) return;

  event.preventDefault();
  eventsPanelResizeState = {
    startX: event.clientX,
    startWidth: state.eventsPanelWidth,
  };
  document.body.dataset.eventsResizing = 'true';

  const handlePointerMove = (moveEvent) => {
    if (!eventsPanelResizeState) return;
    const delta = eventsPanelResizeState.startX - moveEvent.clientX;
    applyEventsPanelWidth(eventsPanelResizeState.startWidth + delta);
  };

  const handlePointerUp = () => {
    if (!eventsPanelResizeState) return;
    eventsPanelResizeState = null;
    delete document.body.dataset.eventsResizing;
    applyEventsPanelWidth(state.eventsPanelWidth, { persist: true });
    window.removeEventListener('pointermove', handlePointerMove);
    window.removeEventListener('pointerup', handlePointerUp);
    window.removeEventListener('pointercancel', handlePointerUp);
  };

  window.addEventListener('pointermove', handlePointerMove);
  window.addEventListener('pointerup', handlePointerUp);
  window.addEventListener('pointercancel', handlePointerUp);
}

function syncEventCardLayout(card, options = {}) {
  const { forceCollapsed = true } = options;
  const textElement = card.querySelector('.event-description-text');
  const toggle = card.querySelector('.event-description-toggle');
  if (!textElement || !toggle) return;

  const previousExpanded = card.classList.contains('is-expanded');

  card.classList.remove('is-expanded');
  card.classList.add('event-card--collapsible');
  textElement.classList.remove('is-clamped');
  textElement.style.removeProperty('--event-description-clamp-lines');
  toggle.hidden = false;
  toggle.style.visibility = 'hidden';

  if (card.scrollHeight <= EVENT_CARD_MAX_HEIGHT + 1) {
    card.classList.remove('event-card--collapsible');
    toggle.hidden = true;
    toggle.style.visibility = '';
    toggle.setAttribute('aria-expanded', 'false');
    toggle.textContent = '...see more';
    return;
  }

  const textStyle = window.getComputedStyle(textElement);
  const lineHeight = Number.parseFloat(textStyle.lineHeight) || 22;
  const fullTextHeight = textElement.getBoundingClientRect().height;
  const maxLines = Math.max(1, Math.ceil(fullTextHeight / lineHeight));

  let low = 1;
  let high = maxLines;
  let bestLines = 1;

  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    textElement.classList.add('is-clamped');
    textElement.style.setProperty('--event-description-clamp-lines', String(mid));
    const fitsWithinCard = card.scrollHeight <= EVENT_CARD_MAX_HEIGHT + 1;

    if (fitsWithinCard) {
      bestLines = mid;
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }

  const shouldCollapse = bestLines < maxLines;

  if (!shouldCollapse) {
    card.classList.remove('event-card--collapsible');
    textElement.classList.remove('is-clamped');
    textElement.style.removeProperty('--event-description-clamp-lines');
    toggle.hidden = true;
    toggle.style.visibility = '';
    toggle.setAttribute('aria-expanded', 'false');
    toggle.textContent = '...see more';
    return;
  }

  textElement.classList.add('is-clamped');
  textElement.style.setProperty('--event-description-clamp-lines', String(bestLines));
  toggle.hidden = false;
  toggle.style.visibility = '';

  if (previousExpanded && !forceCollapsed) {
    card.classList.add('is-expanded');
    textElement.classList.remove('is-clamped');
    textElement.style.removeProperty('--event-description-clamp-lines');
    toggle.setAttribute('aria-expanded', 'true');
    toggle.textContent = 'see less';
    return;
  }

  textElement.classList.add('is-clamped');
  toggle.setAttribute('aria-expanded', 'false');
  toggle.textContent = '...see more';
}

function scheduleEventCardLayoutSync() {
  if (!elements.eventsList) return;
  if (eventCardsLayoutFrame !== null) return;

  eventCardsLayoutFrame = window.requestAnimationFrame(() => {
    eventCardsLayoutFrame = null;
    elements.eventsList.querySelectorAll('.event-card').forEach((card) => {
      syncEventCardLayout(card);
    });
  });
}

function setupEventCardLayoutObserver() {
  if (!elements.eventsPanel || eventCardsResizeObserver) return;

  if (typeof ResizeObserver === 'undefined') {
    window.addEventListener('resize', scheduleEventCardLayoutSync);
    return;
  }

  eventCardsResizeObserver = new ResizeObserver(() => {
    scheduleEventCardLayoutSync();
  });
  eventCardsResizeObserver.observe(elements.eventsPanel);
}

function getAssistantAvatarMarkup() {
  return `
    <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <path d="M4.5 9.25L12 5L19.5 9.25" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M6 10.5H18" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>
      <path d="M7.5 10.75V17" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>
      <path d="M12 10.75V17" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>
      <path d="M16.5 10.75V17" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>
      <path d="M5.5 19H18.5" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/>
    </svg>
  `;
}

function showView(name) {
  elements.authView.hidden = name !== 'auth';
  elements.profileView.hidden = name !== 'profile';
  elements.appView.hidden = name !== 'app';
}

function resetAppState() {
  state.user = null;
  state.threads = [];
  state.activeThreadId = null;
  state.messages = [];
  state.messageVersion = 0;
  state.currentFlagLogId = null;
  state.threadModalMode = null;
  state.threadModalThreadId = null;
  closeFlagModal();
  closeThreadModal();
  renderThreads();
  updateThreadHeader();
  renderMessages();
}

function forceSignedOut(message = 'Your session expired. Sign in again.') {
  resetAppState();
  setError(elements.authError, message);
  setError(elements.profileError, '');
  setError(elements.chatError, '');
  showView('auth');
}

function handleAuthFailure(result, message) {
  if (result && result.status === 401) {
    forceSignedOut(message);
    return true;
  }
  return false;
}

function setError(element, message) {
  if (!element) return;
  if (message) {
    element.textContent = message;
    element.hidden = false;
  } else {
    element.textContent = '';
    element.hidden = true;
  }
}

function showToast(message, tone = 'default') {
  if (!elements.toastStack || !message) return;
  const toast = document.createElement('div');
  toast.className = `toast toast--${tone}`;
  toast.textContent = message;
  elements.toastStack.appendChild(toast);
  window.setTimeout(() => {
    toast.classList.add('toast--leaving');
    window.setTimeout(() => toast.remove(), 180);
  }, 3200);
}

function formatTime(timeStr) {
  if (!timeStr) return '';
  const [hours, minutes] = String(timeStr).split(':');
  const numericHours = Number.parseInt(hours, 10);
  if (Number.isNaN(numericHours)) return timeStr;
  const ampm = numericHours >= 12 ? 'PM' : 'AM';
  const h12 = numericHours % 12 || 12;
  return `${h12}:${minutes || '00'} ${ampm}`;
}

function formatDate(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function formatSource(source) {
  if (source.type === 'sql' && source.table) {
    const key = source.table.toLowerCase();
    return sourceMapping[key] || { label: source.table, path: null };
  }
  if (source.type === 'rag' && source.source) {
    return { label: source.source, path: source.path || null };
  }
  return { label: 'Community data', path: null };
}

function setAuthMode(mode) {
  state.authMode = mode;
  elements.tabLogin.classList.toggle('active', mode === 'login');
  elements.tabSignup.classList.toggle('active', mode === 'signup');
  elements.loginForm.hidden = mode !== 'login';
  elements.signupForm.hidden = mode !== 'signup';
  setError(elements.authError, '');
}

function renderUser() {
  if (!state.user) return;
  elements.accountUsername.textContent = state.user.username || 'Pending profile';
  elements.accountEmail.textContent = state.user.email || '—';
  elements.accountProviders.innerHTML = '';
  (state.user.linked_providers || []).forEach((provider) => {
    const pill = document.createElement('span');
    pill.className = 'provider-pill';
    pill.textContent = providerLabels[provider] || provider;
    elements.accountProviders.appendChild(pill);
  });

  const hasGoogle = Boolean(state.user.has_google);
  elements.googleLinkToggle.textContent = hasGoogle ? 'Unlink Google' : 'Link Google';
  elements.googleLinkToggle.dataset.mode = hasGoogle ? 'unlink' : 'link';
  elements.googleLinkToggle.disabled = false;
  elements.googleLinkToggle.title = !state.googleEnabled && !hasGoogle
    ? 'Google OAuth is not configured on this server.'
    : '';
  elements.adminLink.classList.toggle('hidden', state.user.role !== 'admin');
}

function renderThreads() {
  elements.threadList.innerHTML = '';
  if (!state.threads.length) {
    const empty = document.createElement('div');
    empty.className = 'thread-empty';
    empty.innerHTML = `
      <strong>No saved conversations</strong>
      <span>Start a thread to keep follow-ups and flagged responses tied to your account.</span>
    `;
    elements.threadList.appendChild(empty);
    return;
  }

  state.threads.forEach((thread) => {
    const item = document.createElement('div');
    item.className = `thread-item${thread.id === state.activeThreadId ? ' active' : ''}`;
    item.dataset.threadId = thread.id;

    const body = document.createElement('div');
    body.className = 'thread-item-body';
    body.innerHTML = `
      <div class="thread-item-title">${escapeHtml(thread.title)}</div>
      <div class="thread-item-preview">${escapeHtml(thread.last_message_preview || 'No messages yet')}</div>
      <div class="thread-item-meta">${escapeHtml(formatDate(thread.last_message_at || thread.created_at))}</div>
    `;

    const actions = document.createElement('div');
    actions.className = 'thread-actions';
    actions.innerHTML = `
      <button class="thread-action thread-action--delete" type="button" data-action="delete" aria-label="Delete conversation">
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path d="M9 4H15L16 6H20" />
          <path d="M4 6H20" />
          <path d="M18 6L17.25 19C17.2 19.6 16.7 20 16.1 20H7.9C7.3 20 6.8 19.6 6.75 19L6 6" />
          <path d="M10 10V16" />
          <path d="M14 10V16" />
        </svg>
      </button>
    `;

    item.appendChild(body);
    item.appendChild(actions);
    elements.threadList.appendChild(item);
  });
}

function renderMessages() {
  elements.chatMessages.innerHTML = '';
  elements.suggestions.hidden = !state.messages.length;
  if (!state.messages.length) {
    const empty = createEmptyStateElement();
    elements.chatMessages.appendChild(empty);
    elements.chatMessages.scrollTop = 0;
    return;
  }

  state.messages.forEach((message) => {
    elements.chatMessages.appendChild(createMessageElement(message));
  });
  elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
}

function createEmptyStateElement() {
  const prompts = [
    {
      tone: 'records',
      label: 'Records',
      query: 'Summarize the latest city council minutes related to Dorchester transportation projects.',
    },
    {
      tone: 'policy',
      label: 'Policy',
      query: 'What zoning rules apply to mixed-use development proposals in Dorchester?',
    },
    {
      tone: 'community',
      label: 'Community',
      query: 'Draft a response to neighbors about upcoming park improvements, citing approved budget details.',
      wide: true,
    },
  ];

  const wrapper = document.createElement('section');
  wrapper.className = 'conversation-empty';

  const heading = document.createElement('h2');
  heading.className = 'conversation-empty-title';
  heading.textContent = 'How can I assist you today?';
  wrapper.appendChild(heading);

  const grid = document.createElement('div');
  grid.className = 'conversation-empty-grid';

  prompts.forEach((prompt) => {
    const card = document.createElement('button');
    card.type = 'button';
    card.className = `empty-state-card empty-state-card--${prompt.tone}`;
    if (prompt.wide) {
      card.classList.add('empty-state-card--wide');
    }
    card.dataset.query = prompt.query;
    card.innerHTML = `
      <span class="empty-state-card-label">${escapeHtml(prompt.label)}</span>
      <span class="empty-state-card-copy">${escapeHtml(prompt.query)}</span>
    `;
    card.addEventListener('click', () => {
      elements.chatInput.value = prompt.query;
      elements.chatInput.focus();
    });
    grid.appendChild(card);
  });

  wrapper.appendChild(grid);
  return wrapper;
}

function createMessageElement(message) {
  const wrapper = document.createElement('div');
  wrapper.className = `message ${message.role}`;

  const avatar = document.createElement('div');
  avatar.className = 'message-avatar';
  if (message.role === 'assistant') {
    avatar.classList.add('message-avatar--assistant');
    avatar.innerHTML = getAssistantAvatarMarkup();
  } else {
    avatar.textContent = '👤';
  }

  const content = document.createElement('div');
  content.className = 'message-content';

  const text = document.createElement('div');
  text.className = 'message-text';
  text.innerHTML = formatRichText(message.content);
  content.appendChild(text);

  if (Array.isArray(message.sources) && message.sources.length > 0) {
    const meta = document.createElement('div');
    meta.className = 'message-meta';
    const label = document.createElement('span');
    label.className = 'meta-label';
    label.textContent = 'Sources';
    meta.appendChild(label);

    const seen = new Set();
    message.sources.forEach((source) => {
      const formatted = formatSource(source);
      if (seen.has(formatted.label)) return;
      seen.add(formatted.label);
      const pill = document.createElement('span');
      pill.className = 'meta-pill';
      if (formatted.path) {
        const anchor = document.createElement('a');
        anchor.href = formatted.path;
        anchor.textContent = formatted.label;
        anchor.target = '_blank';
        anchor.rel = 'noreferrer';
        pill.appendChild(anchor);
      } else {
        pill.textContent = formatted.label;
      }
      meta.appendChild(pill);
    });
    content.appendChild(meta);
  }

  if (message.role === 'assistant' && message.log_id) {
    const tools = document.createElement('div');
    tools.className = 'message-tools';
    const flagButton = document.createElement('button');
    flagButton.className = 'flag-button';
    flagButton.type = 'button';
    flagButton.innerHTML = '<span aria-hidden="true">⚑</span><span>Flag</span>';
    flagButton.addEventListener('click', () => openFlagModal(message.log_id));
    tools.appendChild(flagButton);
    content.appendChild(tools);
  }

  wrapper.appendChild(avatar);
  wrapper.appendChild(content);
  return wrapper;
}

function renderTypingIndicator() {
  removeTypingIndicator();
  const wrapper = document.createElement('div');
  wrapper.className = 'message assistant';
  wrapper.id = 'typing-indicator';

  const phrases = [
    'Thinking',
    'Retrieving info from sources',
    'Gathering relevant context',
    'Checking recent updates',
    'Drafting a clear answer',
    'Double-checking details',
    'Finalizing response',
  ];

  const longWaitPhrases = [
    'This is taking longer than usual',
    'Still working—almost there',
  ];

  const intervalMs = () => (inLongWaitMode ? 10000 : 5000);

  wrapper.innerHTML = `
    <div class="message-avatar message-avatar--assistant">${getAssistantAvatarMarkup()}</div>
    <div class="message-content message-content--loading">
      <div class="loading-status" aria-live="polite" aria-label="Assistant is thinking">
        <span class="loading-status__icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path fill="currentColor" d="M19.14 12.94c.04-.31.06-.63.06-.94s-.02-.63-.06-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.11-.2-.36-.28-.57-.2l-2.39.96c-.5-.38-1.04-.69-1.64-.92l-.36-2.54A.487.487 0 0 0 14.36 2h-3.72c-.24 0-.44.17-.48.41l-.36 2.54c-.6.23-1.14.54-1.64.92l-2.39-.96c-.21-.08-.46 0-.57.2L3.28 8.43c-.11.2-.06.47.12.61l2.03 1.58c-.04.31-.06.63-.06.94s.02.63.06.94L3.4 14.52a.5.5 0 0 0-.12.61l1.92 3.32c.11.2.36.28.57.2l2.39-.96c.5.38 1.04.69 1.64.92l.36 2.54c.04.24.24.41.48.41h3.72c.24 0 .44-.17.48-.41l.36-2.54c.6-.23 1.14-.54 1.64-.92l2.39.96c.21.08.46 0 .57-.2l1.92-3.32a.5.5 0 0 0-.12-.61l-2.03-1.58ZM12 15.5c-1.93 0-3.5-1.57-3.5-3.5S10.07 8.5 12 8.5s3.5 1.57 3.5 3.5-1.57 3.5-3.5 3.5Z"/>
          </svg>
        </span>
        <span class="loading-status__label" id="loading-status-label">${phrases[0]}<span class="loading-status__ellipsis" aria-hidden="true">…</span></span>
      </div>
    </div>
  `;
  elements.chatMessages.appendChild(wrapper);
  elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;

  const label = wrapper.querySelector('#loading-status-label');
  if (!label) return;

  const stateKey = '__loadingStatusInterval';
  if (window[stateKey]) {
    window.clearTimeout(window[stateKey]);
  }

  let phraseIndex = 0;
  let longWaitIndex = 0;
  let inLongWaitMode = false;
  const advance = () => {
    if (!inLongWaitMode) {
      if (phraseIndex < phrases.length - 1) {
        phraseIndex += 1;
      } else {
        inLongWaitMode = true;
        longWaitIndex = 0;
      }
    } else {
      longWaitIndex = (longWaitIndex + 1) % longWaitPhrases.length;
    }
    label.classList.add('is-transitioning');
    window.setTimeout(() => {
      const nextText = inLongWaitMode ? longWaitPhrases[longWaitIndex] : phrases[phraseIndex];
      label.innerHTML = `${nextText}<span class="loading-status__ellipsis" aria-hidden="true">…</span>`;
      label.classList.remove('is-transitioning');
    }, 220);
  };

  // Kick off rotation after a short delay so the first state is stable.
  const schedule = () => {
    const ms = intervalMs();
    window[stateKey] = window.setTimeout(() => {
      advance();
      schedule();
    }, ms);
  };
  schedule();
}

function removeTypingIndicator() {
  const indicator = document.getElementById('typing-indicator');
  if (indicator) indicator.remove();

  const stateKey = '__loadingStatusInterval';
  if (window[stateKey]) {
    window.clearTimeout(window[stateKey]);
    window[stateKey] = null;
  }
}

function setChatLoading(loading) {
  state.isSendingMessage = loading;
  elements.chatInput.disabled = loading;
  elements.chatSubmit.disabled = loading;
  elements.chatInput.placeholder = loading ? '...' : CHAT_INPUT_PLACEHOLDER;
}

function setEventsLoading(loading) {
  state.isLoadingEvents = loading;
  elements.eventsLoading.hidden = !loading;
}

function formatEventDate(isoDate, fallbackText) {
  if (!isoDate) return fallbackText || 'Upcoming';
  const [year, month, day] = isoDate.split('-').map(Number);
  const d = new Date(year, month - 1, day);
  return d.toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric'
  });
}
function renderEvents(events) {
  elements.eventsList.innerHTML = '';
  elements.eventsEmpty.hidden = events.length > 0;
  events.forEach((event, index) => {
    const card = document.createElement('div');
    card.className = 'event-card';
    const date = formatEventDate(event.start_date, event.event_date);
    const start = formatTime(event.start_time);
    const end = formatTime(event.end_time);
    const timeLabel = start && end ? `${start} - ${end}` : (start || '');
    const description = String(event.description || 'No description available.');
    const descriptionId = `event-description-${index}`;

    card.innerHTML = `
      <div class="event-date">${escapeHtml(date)}</div>
      <div class="event-title">${escapeHtml(event.event_name || 'Community Event')}</div>
      ${timeLabel ? `<div class="event-time">${escapeHtml(timeLabel)}</div>` : ''}
      <div class="event-description">
        <div class="event-description-text is-clamped" id="${descriptionId}">${escapeHtml(description)}</div>
        <button class="event-description-toggle" type="button" data-description-id="${descriptionId}" aria-expanded="false" hidden>...see more</button>
      </div>
    `;

    card.addEventListener('click', (clickEvent) => {
      const toggle = clickEvent.target.closest('.event-description-toggle');
      if (toggle) {
        clickEvent.preventDefault();
        clickEvent.stopPropagation();
        const targetId = toggle.dataset.descriptionId;
        const textElement = targetId ? document.getElementById(targetId) : null;
        if (!textElement) return;

        const expanded = card.classList.toggle('is-expanded');
        textElement.classList.toggle('is-clamped', !expanded);
        toggle.setAttribute('aria-expanded', String(expanded));
        toggle.textContent = expanded ? 'see less' : '...see more';
        return;
      }

      const eventName = event.event_name || 'this event';
      elements.chatInput.value = `Tell me more about "${eventName}" event happening on ${date}.`;
      elements.chatInput.focus();
    });
    elements.eventsList.appendChild(card);
    syncEventCardLayout(card);
  });
  scheduleEventCardLayoutSync();
}

function updateThreadHeader() {
  const thread = state.threads.find((entry) => entry.id === state.activeThreadId);
  elements.activeThreadTitle.textContent = thread ? thread.title : 'New conversation';
  elements.renameThreadButton.disabled = !thread;
  elements.deleteThreadButton.disabled = !thread;
}

function formatRichText(text) {
  const escaped = escapeHtml(String(text || ''))
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>');
  return escaped.split('<br>').map((paragraph) => paragraph.trim() ? `<p>${paragraph}</p>` : '').join('');
}

function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function parseMessageTimestamp(message) {
  const timestamp = message?.created_at;
  if (!timestamp) return Number.NaN;
  const parsed = new Date(timestamp).getTime();
  return Number.isNaN(parsed) ? Number.NaN : parsed;
}

function normalizeMessages(messages) {
  const deduped = new Map();

  messages.forEach((message, index) => {
    if (!message || typeof message !== 'object') return;
    const key = message.id || `__temp_${index}`;
    if (deduped.has(key)) {
      const existing = deduped.get(key);
      deduped.set(key, { ...existing, ...message, __index: existing.__index });
      return;
    }
    deduped.set(key, { ...message, __index: index });
  });

  const ordered = Array.from(deduped.values()).sort((left, right) => {
    const leftTime = parseMessageTimestamp(left);
    const rightTime = parseMessageTimestamp(right);
    const leftValid = Number.isFinite(leftTime);
    const rightValid = Number.isFinite(rightTime);

    if (leftValid && rightValid && leftTime !== rightTime) {
      return leftTime - rightTime;
    }
    if (leftValid && !rightValid) return -1;
    if (!leftValid && rightValid) return 1;
    return (left.__index || 0) - (right.__index || 0);
  });

  for (let index = 0; index < ordered.length - 1; index += 1) {
    const current = ordered[index];
    const next = ordered[index + 1];
    const sameTimestamp = current?.created_at && current.created_at === next?.created_at;
    if (sameTimestamp && current?.role === 'assistant' && next?.role === 'user') {
      ordered[index] = next;
      ordered[index + 1] = current;
      index += 1;
    }
  }

  return ordered.map(({ __index, ...message }) => message);
}

function parseAuthErrorCode(code) {
  const map = {
    google_oauth_disabled: 'Google sign-in is not configured on this server yet.',
    google_oauth_failed: 'Google sign-in failed. Try again.',
    google_email_not_verified: 'Google returned an unverified email address.',
    existing_account_requires_password_login: 'This email already has an account. Sign in with your password, then link Google from inside the app.',
    google_email_mismatch: 'The Google account email did not match your existing account email.',
    google_account_already_linked: 'That Google account is already linked to another user.',
    login_required_for_link: 'Sign in before linking Google.',
    oauth_link_session_mismatch: 'Your linking session expired. Start the link flow again.',
  };
  return map[code] || '';
}

async function refreshSession() {
  const result = await ApiClient.getSession();
  if (!result.success) {
    resetAppState();
    setError(elements.authError, result.error);
    showView('auth');
    return false;
  }

  state.user = result.data.user || null;
  state.googleEnabled = Boolean(result.data.google_oauth_enabled);
  elements.googleAuthButton.title = !state.googleEnabled
    ? 'Google OAuth is not configured on this server.'
    : '';

  const oauthError = new URLSearchParams(window.location.search).get('auth_error');
  if (oauthError) {
    window.history.replaceState({}, document.title, window.location.pathname);
    setError(elements.authError, parseAuthErrorCode(oauthError));
  }

  if (!state.user) {
    resetAppState();
    showView('auth');
    return false;
  }

  if (!state.user.profile_complete) {
    renderUser();
    showView('profile');
    return true;
  }

  showView('app');
  renderUser();
  await ensureInitialData();
  return true;
}

async function ensureInitialData() {
  await Promise.all([loadThreads(), loadEvents(), updateApiStatus()]);
}

async function loadThreads(selectThreadId = null) {
  const result = await ApiClient.fetchThreads();
  if (!result.success) {
    if (handleAuthFailure(result)) return;
    setError(elements.chatError, result.error);
    return;
  }

  state.threads = result.data.threads || [];
  if (!state.threads.length) {
    const created = await ApiClient.createThread({});
    if (!created.success) {
      if (handleAuthFailure(created)) return;
      setError(elements.chatError, created.error);
      return;
    }
    state.threads = [created.data.thread];
  }

  const nextId = selectThreadId && state.threads.some((thread) => thread.id === selectThreadId)
    ? selectThreadId
    : (state.activeThreadId && state.threads.some((thread) => thread.id === state.activeThreadId)
      ? state.activeThreadId
      : state.threads[0].id);

  state.activeThreadId = nextId;
  renderThreads();
  updateThreadHeader();
  await loadMessages(nextId);
}

async function loadMessages(threadId) {
  const requestVersion = ++state.messageVersion;
  const result = await ApiClient.fetchMessages(threadId, { limit: 50 });
  if (!result.success) {
    if (handleAuthFailure(result)) return;
    if (result.status === 409 && result.data && result.data.code === 'profile_incomplete') {
      showView('profile');
      return;
    }
    setError(elements.chatError, result.error);
    return;
  }

  if (requestVersion !== state.messageVersion) {
    return;
  }

  state.activeThreadId = threadId;
  state.messages = normalizeMessages(result.data.messages || []);
  const thread = result.data.thread;
  if (thread) {
    const index = state.threads.findIndex((entry) => entry.id === thread.id);
    if (index >= 0) {
      state.threads[index] = thread;
    }
  }
  renderThreads();
  updateThreadHeader();
  renderMessages();
}

async function createThread() {
  setError(elements.chatError, '');
  state.messageVersion += 1;
  const result = await ApiClient.createThread({});
  if (!result.success) {
    if (handleAuthFailure(result)) return;
    setError(elements.chatError, result.error);
    return;
  }
  state.threads.unshift(result.data.thread);
  state.activeThreadId = result.data.thread.id;
  state.messages = [];
  renderThreads();
  updateThreadHeader();
  renderMessages();
}

async function renameThread(threadId = state.activeThreadId) {
  const thread = state.threads.find((entry) => entry.id === threadId);
  if (!thread) return;
  state.threadModalMode = 'rename';
  state.threadModalThreadId = thread.id;
  elements.threadModalTitle.textContent = 'Rename conversation';
  elements.threadModalCopy.textContent = 'Give this thread a title you can recognize later.';
  elements.threadModalField.hidden = false;
  elements.threadModalInput.value = thread.title || '';
  elements.threadModalConfirm.textContent = 'Save';
  elements.threadModalConfirm.classList.remove('danger-solid');
  setError(elements.threadModalError, '');
  elements.threadModal.hidden = false;
  window.setTimeout(() => {
    elements.threadModalInput.focus();
    elements.threadModalInput.select();
  }, 0);
}

async function submitRenameThread() {
  const threadId = state.threadModalThreadId;
  const thread = state.threads.find((entry) => entry.id === threadId);
  if (!thread) {
    closeThreadModal();
    return;
  }
  const trimmed = elements.threadModalInput.value.trim();
  if (!trimmed) {
    setError(elements.threadModalError, 'Enter a conversation title.');
    elements.threadModalInput.focus();
    return;
  }
  const result = await ApiClient.updateThread(thread.id, { title: trimmed });
  if (!result.success) {
    if (handleAuthFailure(result)) return;
    setError(elements.threadModalError, result.error);
    return;
  }
  const index = state.threads.findIndex((entry) => entry.id === thread.id);
  state.threads[index] = result.data.thread;
  renderThreads();
  updateThreadHeader();
  closeThreadModal();
  showToast('Conversation renamed.', 'success');
}

async function deleteThread(threadId = state.activeThreadId) {
  const thread = state.threads.find((entry) => entry.id === threadId);
  if (!thread) return;
  state.threadModalMode = 'delete';
  state.threadModalThreadId = thread.id;
  elements.threadModalTitle.textContent = 'Delete conversation';
  elements.threadModalCopy.textContent = `Delete "${thread.title}" and remove it from your sidebar.`;
  elements.threadModalField.hidden = true;
  elements.threadModalInput.value = '';
  elements.threadModalConfirm.textContent = 'Delete';
  elements.threadModalConfirm.classList.add('danger-solid');
  setError(elements.threadModalError, '');
  elements.threadModal.hidden = false;
  window.setTimeout(() => elements.threadModalConfirm.focus(), 0);
}

async function submitDeleteThread() {
  const threadId = state.threadModalThreadId;
  const thread = state.threads.find((entry) => entry.id === threadId);
  if (!thread) {
    closeThreadModal();
    return;
  }
  const result = await ApiClient.deleteThread(thread.id);
  if (!result.success) {
    if (handleAuthFailure(result)) return;
    setError(elements.threadModalError, result.error);
    return;
  }
  state.threads = state.threads.filter((entry) => entry.id !== thread.id);
  state.activeThreadId = null;
  state.messages = [];
  state.messageVersion += 1;
  renderThreads();
  updateThreadHeader();
  renderMessages();
  if (!state.threads.length) {
    await createThread();
  } else {
    await loadMessages(state.threads[0].id);
  }
  closeThreadModal();
  showToast('Conversation deleted.', 'warning');
}

async function sendChatMessage(event) {
  event.preventDefault();
  if (state.isSendingMessage || !state.activeThreadId) return;
  const message = elements.chatInput.value.trim();
  if (!message) return;
  const threadId = state.activeThreadId;
  const requestVersion = ++state.messageVersion;
  const optimisticMessageId = `pending-user-${Date.now()}-${requestVersion}`;
  const optimisticMessage = {
    id: optimisticMessageId,
    role: 'user',
    content: message,
    created_at: new Date().toISOString(),
    sources: [],
  };

  setError(elements.chatError, '');
  elements.chatInput.value = '';
  state.messages = [
    ...state.messages,
    optimisticMessage,
  ];
  renderMessages();
  setChatLoading(true);
  renderTypingIndicator();

  try {
    const result = await ApiClient.sendMessage(threadId, { message });
    removeTypingIndicator();

    if (!result.success) {
      if (handleAuthFailure(result)) return;
      if (result.status === 409 && result.data && result.data.code === 'profile_incomplete') {
        showView('profile');
        return;
      }
      state.messages = state.messages.filter((entry) => entry.id !== optimisticMessageId);
      renderMessages();
      if (!elements.chatInput.value) {
        elements.chatInput.value = message;
      }
      setError(elements.chatError, result.error);
      return;
    }

    const threadIndex = state.threads.findIndex((entry) => entry.id === result.data.thread.id);
    if (threadIndex >= 0) {
      state.threads[threadIndex] = result.data.thread;
    }

    if (requestVersion !== state.messageVersion || threadId !== state.activeThreadId) {
      renderThreads();
      updateThreadHeader();
      return;
    }

    state.messages = normalizeMessages([
      ...state.messages.filter((entry) => entry.id !== optimisticMessageId),
      result.data.user_message,
      result.data.assistant_message,
    ]);

    renderThreads();
    updateThreadHeader();
    renderMessages();
  } finally {
    removeTypingIndicator();
    setChatLoading(false);
  }
}

async function loadEvents() {
  if (state.isLoadingEvents) return;
  const daysAhead = Number.parseInt(elements.eventsDays.value, 10) || 14;
  const limit = Number.parseInt(elements.eventsLimit.value, 10) || 10;
  setEventsLoading(true);
  setError(elements.eventsError, '');

  const result = await ApiClient.fetchEvents(daysAhead, limit);
  setEventsLoading(false);

  if (!result.success) {
    if (handleAuthFailure(result)) return;
    setError(elements.eventsError, result.error);
    return;
  }

  renderEvents(result.data.events || []);
}

async function updateApiStatus() {
  const result = await ApiClient.health();
  elements.apiStatus.className = 'status-indicator';
  if (!result.success) {
    elements.apiStatus.classList.add('error');
    elements.apiStatus.querySelector('.status-text').textContent = 'Offline';
    return;
  }

  if (result.data.status === 'ok') {
    elements.apiStatus.classList.add('connected');
    elements.apiStatus.querySelector('.status-text').textContent = 'Connected';
  } else {
    elements.apiStatus.classList.add('error');
    elements.apiStatus.querySelector('.status-text').textContent = 'Degraded';
  }
}

function openFlagModal(logId) {
  state.currentFlagLogId = logId;
  document.querySelectorAll('input[name="flag-reason"]').forEach((radio) => {
    radio.checked = false;
  });
  elements.flagDetail.value = '';
  setError(elements.flagError, '');
  elements.flagModal.hidden = false;
}

function closeFlagModal() {
  state.currentFlagLogId = null;
  elements.flagModal.hidden = true;
  setError(elements.flagError, '');
}

function closeThreadModal() {
  state.threadModalMode = null;
  state.threadModalThreadId = null;
  elements.threadModal.hidden = true;
  elements.threadModalConfirm.classList.remove('danger-solid');
  setError(elements.threadModalError, '');
}

async function submitThreadModal() {
  if (state.threadModalMode === 'rename') {
    await submitRenameThread();
    return;
  }
  if (state.threadModalMode === 'delete') {
    await submitDeleteThread();
  }
}

async function submitFlag() {
  const reason = document.querySelector('input[name="flag-reason"]:checked')?.value;
  if (!reason || !state.currentFlagLogId) {
    setError(elements.flagError, 'Select a reason first.');
    return;
  }
  const result = await ApiClient.flagInteraction(state.currentFlagLogId, reason, elements.flagDetail.value.trim());
  if (!result.success) {
    setError(elements.flagError, result.error);
    return;
  }
  closeFlagModal();
  showToast('Report submitted for review.', 'warning');
}

async function handleLogin(event) {
  event.preventDefault();
  setError(elements.authError, '');
  const result = await ApiClient.login({
    email: document.getElementById('login-email').value,
    password: document.getElementById('login-password').value,
  });
  if (!result.success) {
    setError(elements.authError, result.error);
    return;
  }
  await refreshSession();
}

async function handleSignup(event) {
  event.preventDefault();
  setError(elements.authError, '');
  const result = await ApiClient.signup({
    username: document.getElementById('signup-username').value,
    email: document.getElementById('signup-email').value,
    password: document.getElementById('signup-password').value,
  });
  if (!result.success) {
    setError(elements.authError, result.error);
    return;
  }
  await refreshSession();
}

async function handleProfileSubmit(event) {
  event.preventDefault();
  setError(elements.profileError, '');
  const result = await ApiClient.completeProfile({
    username: document.getElementById('profile-username').value,
  });
  if (!result.success) {
    setError(elements.profileError, result.error);
    return;
  }
  await refreshSession();
}

async function handleLogout() {
  await ApiClient.logout();
  resetAppState();
  setError(elements.authError, '');
  setError(elements.profileError, '');
  setError(elements.chatError, '');
  showView('auth');
}

async function handleGoogleLinkToggle() {
  if (elements.googleLinkToggle.dataset.mode === 'unlink') {
    state.threadModalMode = 'unlink-google';
    state.threadModalThreadId = null;
    elements.threadModalTitle.textContent = 'Unlink Google';
    elements.threadModalCopy.textContent = 'Remove Google sign-in from this account. Your password login will remain available.';
    elements.threadModalField.hidden = true;
    elements.threadModalInput.value = '';
    elements.threadModalConfirm.textContent = 'Unlink';
    elements.threadModalConfirm.classList.add('danger-solid');
    setError(elements.threadModalError, '');
    elements.threadModal.hidden = false;
    window.setTimeout(() => elements.threadModalConfirm.focus(), 0);
    return;
  }
  if (!state.googleEnabled) {
    setError(elements.chatError, 'Google sign-in is not configured on this server yet.');
    return;
  }
  window.location.href = ApiClient.googleAuthUrl('link', '/');
}

async function submitUnlinkGoogle() {
  const result = await ApiClient.unlinkGoogle();
  if (!result.success) {
    if (handleAuthFailure(result)) return;
    setError(elements.threadModalError, result.error);
    return;
  }
  state.user = result.data.user;
  renderUser();
  closeThreadModal();
  showToast('Google sign-in removed from this account.', 'warning');
}

function handleModalBackdropClick(event) {
  if (event.target === elements.flagModal) {
    closeFlagModal();
  }
  if (event.target === elements.threadModal) {
    closeThreadModal();
  }
}

function handleGlobalKeydown(event) {
  if (event.key === 'Escape') {
    if (!elements.threadModal.hidden) {
      closeThreadModal();
    } else if (!elements.flagModal.hidden) {
      closeFlagModal();
    }
  }
  if (event.key === 'Enter' && !elements.threadModal.hidden && document.activeElement === elements.threadModalInput) {
    event.preventDefault();
    submitThreadModal();
  }
}

function handleThreadListClick(event) {
  const actionButton = event.target.closest('[data-action]');
  const item = event.target.closest('.thread-item');
  if (!item) return;
  const threadId = item.dataset.threadId;
  if (!threadId) return;

  if (actionButton) {
    const action = actionButton.dataset.action;
    if (action === 'rename') {
      renameThread(threadId);
    } else if (action === 'delete') {
      deleteThread(threadId);
    }
    return;
  }

  loadMessages(threadId);
}


function initEventListeners() {
  elements.tabLogin.addEventListener('click', () => setAuthMode('login'));
  elements.tabSignup.addEventListener('click', () => setAuthMode('signup'));
  elements.loginForm.addEventListener('submit', handleLogin);
  elements.signupForm.addEventListener('submit', handleSignup);
  elements.googleAuthButton.addEventListener('click', () => {
    if (!state.googleEnabled) {
      setError(elements.authError, 'Google sign-in is not configured on this server.');
      return;
    }
    window.location.href = ApiClient.googleAuthUrl('login', '/');
  });
  elements.profileForm.addEventListener('submit', handleProfileSubmit);
  elements.profileLogout.addEventListener('click', handleLogout);
  elements.logoutButton.addEventListener('click', handleLogout);
  elements.googleLinkToggle.addEventListener('click', handleGoogleLinkToggle);
  elements.newThreadButton.addEventListener('click', createThread);
  elements.renameThreadButton.addEventListener('click', () => renameThread());
  elements.deleteThreadButton.addEventListener('click', () => deleteThread());
  elements.themeToggles.forEach((toggle) => {
    toggle.addEventListener('click', toggleTheme);
  });
  elements.eventsPanelToggle.addEventListener('click', toggleEventsPanel);
  if (elements.eventsResizer) {
    elements.eventsResizer.addEventListener('pointerdown', beginEventsPanelResize);
  }
  elements.chatForm.addEventListener('submit', sendChatMessage);
  elements.threadList.addEventListener('click', handleThreadListClick);
  elements.eventsRefresh.addEventListener('click', loadEvents);
  elements.eventsDays.addEventListener('change', loadEvents);
  elements.eventsLimit.addEventListener('change', loadEvents);
  elements.flagCancel.addEventListener('click', closeFlagModal);
  elements.flagSubmit.addEventListener('click', submitFlag);
  elements.flagModal.addEventListener('click', handleModalBackdropClick);
  elements.threadModal.addEventListener('click', handleModalBackdropClick);
  elements.threadModalCancel.addEventListener('click', closeThreadModal);
  elements.threadModalConfirm.addEventListener('click', async () => {
    if (state.threadModalMode === 'unlink-google') {
      await submitUnlinkGoogle();
      return;
    }
    await submitThreadModal();
  });
  document.addEventListener('keydown', handleGlobalKeydown);

  elements.suggestions.addEventListener('click', (event) => {
    const button = event.target.closest('.suggestion-chip');
    if (!button) return;
    elements.chatInput.value = button.dataset.query || '';
    elements.chatInput.focus();
  });


}

async function initApp() {
  applyTheme(getStoredTheme());
  applyEventsPanelWidth(getStoredEventsPanelWidth());
  applyEventsPanelCollapsed(getStoredEventsPanelCollapsed());
  setupEventCardLayoutObserver();
  initEventListeners();
  setAuthMode('login');
  await refreshSession();
  setInterval(updateApiStatus, 30000);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  initApp();
}
