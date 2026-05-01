# Aegis Mail — Gmail summarizer

Mail AI is a small project (CLI + web) that connects to Gmail, fetches messages, and uses AI to produce structured summaries and suggested actions.

Key features
- OAuth Google Sign-in (Gmail read-only scopes)
- Fetch inbox messages (read/unread) with attachments
- Render sanitized HTML email previews (inline styles preserved)
- AI-powered structured summaries (Groq primary, Gemini optional, local fallback)
- Cache summaries and store encrypted Gmail tokens in Supabase
- Serve a React frontend (Vite) with a FastAPI backend