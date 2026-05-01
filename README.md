# Mail AI — Gmail summarizer

Mail AI is a small project (CLI + web) that connects to Gmail, fetches messages, and uses AI to produce structured summaries and suggested actions.

Key features
- OAuth Google Sign-in (Gmail read-only scopes)
- Fetch inbox messages (read/unread) with attachments
- Render sanitized HTML email previews (inline styles preserved)
- AI-powered structured summaries (Groq primary, Gemini optional, local fallback)
- Cache summaries and store encrypted Gmail tokens in Supabase
- Serve a React frontend (Vite) with a FastAPI backend

Quick start (development)
1. Create a Python virtualenv and install dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

2. Frontend setup:

```bash
cd web
npm install
```

3. Environment
- Copy `.env.example` to `.env` and set required values. At minimum for local dev set:

- `GMAIL_CREDENTIALS_PATH` — path to OAuth JSON downloaded from Google Cloud (Web application)
- `SESSION_SECRET` — a random secret for signed sessions
- `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` if using Supabase

4. Run backend (local):

```bash
python -m uvicorn mail_ai.web_ai:app --reload --port 8000
```

5. Run frontend (local):

```bash
cd web
npm run dev
```

6. Open the app at `http://localhost:5173` and sign in with a Google test user (set OAuth consent screen to Testing and add your email as a test user).

Production notes
- Use a verified domain and HTTPS for Google OAuth verification.
- Host the frontend on Vercel/Netlify and the backend on a host such as Fly.io, Railway, or Cloud Run.
- Store secrets (`SUPABASE_SERVICE_ROLE_KEY`, `SESSION_SECRET`, `TOKEN_ENCRYPTION_KEY`) as environment variables on the server — never in frontend code.
- Run the SQL in `sql/supabase_schema.sql` to create the `app_users`, `gmail_tokens`, and `message_summaries` tables (this project uses Supabase REST endpoints).

Security & privacy
- Tokens are encrypted before being stored in Supabase.
- Emails and summaries are sensitive data — disclose usage and deletion instructions in your privacy policy before requesting Google verification.

Developer tips
- For quick dev sign-ins, set the OAuth consent screen to Testing and add test users.
- To persist refreshed OAuth tokens to Supabase, the backend now writes tokens automatically when they are refreshed.
- Use the `sql/SUPABASE_INSTRUCTIONS.md` for step-by-step Supabase setup.

Where to look in the repo
- Backend: `src/mail_ai/web_ai.py` — FastAPI app and OAuth routes
- Gmail client: `src/mail_ai/gmail_client.py`
- Supabase store: `src/mail_ai/supabase_store.py`
- Frontend: `web/src` and `web` (Vite config)
- SQL schema: `sql/supabase_schema.sql`

If you want I can:
- Add a Dockerfile + `fly.toml` for deploying the backend to Fly.io
- Create Vercel deployment config for the frontend
- Draft the OAuth consent screen text, scope justification, and a screencast checklist for verification

Enjoy — tell me which deployment path you'd like and I'll scaffold it.
