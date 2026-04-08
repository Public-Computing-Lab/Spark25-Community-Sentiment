# On The Porch frontend

This frontend now uses server-managed user sessions instead of sending a shared API key from the browser.

## Local run

1. Start MySQL.
2. Start the API from the repo root:
   ```bash
   ./venv/bin/python api/api_v2.py
   ```
3. Serve the static frontend:
   ```bash
   cd public
   python -m http.server 8000
   ```
4. Open:
   ```text
   http://127.0.0.1:8000
   ```

## Auth flow

- `index.html` bootstraps by calling `GET /auth/me`.
- The API sets a readable CSRF cookie and, after login, an `HttpOnly` session cookie.
- Email/password sign-in and account creation go through `/auth/signup` and `/auth/login`.
- Google sign-in is available only when the OAuth environment variables are configured.
- Conversations are loaded from `/conversations` and `/conversations/:id/messages`.
- The chat UI no longer treats in-browser history as the source of truth.

## Admin access

- `admin.html` now relies on the same authenticated session.
- Only users with `role=admin` can access admin endpoints.
- There is no client-side admin password anymore.

## Runtime configuration

`api.js` uses this order when choosing the API base URL:

1. `window.APP_CONFIG.apiBaseUrl` from `public/config.js`
2. `window.APP_CONFIG.API_BASE_URL` from `public/config.js`
3. `http://127.0.0.1:8888` when the frontend is served from port `8000`
4. same-origin relative requests for production-style deployments

Optional timeout overrides in `public/config.js`:

- `window.APP_CONFIG.requestTimeoutMs`: default timeout for normal API calls
- `window.APP_CONFIG.chatTimeoutMs`: timeout for `/conversations/:id/messages`

By default, normal API calls time out after 30 seconds, but chat requests do not auto-timeout in the browser.

## Files

- `index.html`: auth, profile-completion, chat, and events UI
- `app.js`: session bootstrap, thread management, and chat behavior
- `api.js`: cookie-based API client with CSRF header handling
- `config.js`: optional runtime API-base override
- `admin.html`: authenticated admin dashboard
- `styles.css`: shared frontend styling

## Troubleshooting

- `401 auth_required`: you are not signed in, or your session expired
- `403 csrf_failed`: load the app first so `/auth/me` can seed the CSRF cookie, then retry
- `409 profile_incomplete`: finish choosing a username before using chat
- `503 google_oauth_disabled`: Google OAuth environment variables are not configured on the API server
