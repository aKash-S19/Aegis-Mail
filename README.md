<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/your-org/aegis/main/web/public/logo2.png">
  <img alt="Aegis Mail" src="https://raw.githubusercontent.com/your-org/aegis/main/web/public/logo2.png" width="80">
</picture>

# Aegis Mail

**Your AI inbox assistant — summarizes emails, explains context, and tells you what to do.**

Stop drowning in email. Aegis connects to your Gmail, runs every message through AI, and gives you a clean, structured breakdown: what it is, why you got it, what matters, and what you should do next.

---

## What it does

- **AI summaries** — Groq (or Gemini) reads each email and distills it into a clear summary, topic, and category
- **Action items** — extracts tasks, deadlines, and next steps
- **Context & jargon** — explains why you received the email
- **Classification** — flags marketing, newsletters, important messages, and potential concerns
- **Full email rendering** — sanitized HTML preview or expandable plain text

## Built with

| Frontend | Backend | AI | Auth & Storage |
|---|---|---|---|
| React + Vite | FastAPI (Python) | Groq / Gemini / local fallback | Firebase Auth |
| CSS (no framework) | Gmail API | Structured JSON extraction | Firestore / Supabase |
