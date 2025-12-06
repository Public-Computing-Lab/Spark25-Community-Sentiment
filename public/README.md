# On The Porch - Frontend

A simple frontend for the Dorchester Community Assistant chatbot.

## Quick Start

1. **Start the backend API:**
   ```bash
   cd ml-misi-community-sentiment
   python api/api_v2.py
   ```

2. **Serve the frontend:**
   ```bash
   # From project root
   cd public
   python -m http.server 8000
   ```

3. **Open in browser:**
   ```
   http://localhost:8000
   ```

## Configuration

### API Connection

Edit `app.js` or `api.js` to configure the API connection:

```javascript
const API_BASE_URL = 'http://127.0.0.1:8888';
const API_KEY = 'banana';  // Must match backend RETHINKAI_API_KEYS
```

### API Authentication

The frontend requires a valid API key. The default is `'banana'` which matches the backend default.

If you've changed the backend keys in `.env`, update the `API_KEY` in both `app.js` and `api.js`.

## Files

- `index.html` - Main page structure
- `app.js` - Main application logic
- `api.js` - API client with error handling
- `styles.css` - Styling

## Features

- Chat interface with conversation history
- Upcoming events sidebar
- Source citations for responses
- API status indicator
- Quick suggestion chips

## Troubleshooting

**401 Unauthorized:**
- Check that `API_KEY` matches `RETHINKAI_API_KEYS` in backend `.env`

**Connection errors:**
- Make sure backend is running on port 8888
- Check browser console for details

**Events not loading:**
- Verify MySQL database is running and accessible
- Check that `weekly_events` table exists

