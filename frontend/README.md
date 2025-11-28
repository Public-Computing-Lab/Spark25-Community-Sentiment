# Dorchester Community Assistant - Frontend

A simple, modern frontend for testing and interacting with the Agent API v2.0.

## Features

### 1. Community Chat
- Real-time chat interface with the AI assistant
- Conversation history maintained for context
- Source citations displayed with responses
- Quick hint chips for common questions
- Shows routing mode (SQL, RAG, hybrid)

### 2. Events Dashboard
- View upcoming community events
- Filter by days ahead (7, 14, 30 days)
- Adjustable result limit
- Event cards with date, time, and description

### 3. API Tester
- Test all API endpoints directly
- Supports GET, POST, PUT methods
- JSON request body editor
- Response viewer with status codes and timing

## Quick Start

### Prerequisites
- Python 3.x (for the HTTP server)
- API server running on `http://127.0.0.1:8888`

### Running the Frontend

1. **Start the API server** (in one terminal):
   ```bash
   cd ml-misi-community-sentiment
   python api/api_v2.py
   ```

2. **Start the frontend server** (in another terminal):
   ```bash
   cd ml-misi-community-sentiment/frontend
   python -m http.server 3000
   ```

3. **Open in browser**:
   ```
   http://localhost:3000
   ```

## File Structure

```
frontend/
├── index.html    # Main HTML structure
├── styles.css    # Styling (dark teal theme)
├── app.js        # JavaScript logic
└── README.md     # This file
```

## Configuration

The API base URL is configured in `app.js`:

```javascript
const API_BASE_URL = 'http://127.0.0.1:8888';
```

Change this if your API is running on a different host/port.

## Design

- **Theme**: Dark teal/forest color scheme
- **Font**: DM Sans (UI), JetBrains Mono (code)
- **Layout**: Sidebar navigation with main content area
- **Responsive**: Adapts to smaller screens

## API Status Indicator

The green dot in the sidebar footer shows the API connection status:
- 🟢 Green = API connected
- 🔴 Red = API offline/error

Status is checked every 30 seconds automatically.

## Browser Compatibility

Tested on:
- Chrome/Edge (Chromium)
- Firefox
- Safari

## Development

This is a vanilla HTML/CSS/JS frontend - no build tools required. Simply edit the files and refresh the browser.

### Adding New Features

1. **New View**: Add a section in `index.html`, style in `styles.css`, logic in `app.js`
2. **New API Endpoint**: Add option to the endpoint selector in `index.html` and handle in `sendApiRequest()` in `app.js`

## Screenshots

### Chat View
![Chat View](screenshots/chat-view.png)

### Events View
![Events View](screenshots/events-view.png)

### API Tester
![API Tester](screenshots/api-tester.png)

