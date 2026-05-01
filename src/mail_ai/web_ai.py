from __future__ import annotations

import logging
import os
import re
import secrets
from pathlib import Path
from typing import Optional, Union

import bleach
from bleach.css_sanitizer import CSSSanitizer
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
import json

from google.oauth2.credentials import Credentials as OAuth2Credentials

from .supabase_store import SupabaseStore, SupabaseConfig

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from .config import load_settings
from .gmail_client import GmailClient, SCOPES_READONLY
from .summarize import GeminiSummarizer, GroqSummarizer, LocalHeuristicSummarizer
from .models import EmailMessage, SummaryResult


settings = load_settings()
logger = logging.getLogger("mail_ai.web")
FRONTEND_URL = os.getenv("WEB_FRONTEND_URL", "http://localhost:5173")
ALLOWED_ORIGINS = list(
    dict.fromkeys(
        [
            FRONTEND_URL,
            "http://localhost:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:5174",
        ]
    )
)
REDIRECT_URI = os.getenv(
    "WEB_REDIRECT_URI", "http://localhost:8000/auth/google/callback"
)
TOKEN_DIR = Path(os.getenv("TOKEN_DIR", "tokens"))
TOKEN_DIR.mkdir(parents=True, exist_ok=True)

# Initialize Supabase store when configured
SUPABASE_STORE: SupabaseStore | None = None
if settings.supabase_url and settings.supabase_service_role_key:
    SUPABASE_STORE = SupabaseStore(
        SupabaseConfig(
            url=settings.supabase_url,
            service_role_key=settings.supabase_service_role_key,
            token_encryption_key=settings.token_encryption_key,
        )
    )

app = FastAPI(title="Mail AI Manager", version="0.1.0")

session_secret = settings.session_secret or secrets.token_urlsafe(48)
if not settings.session_secret:
    logger.warning("SESSION_SECRET is not set; using a temporary in-memory secret.")

app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret,
    session_cookie="mailai_session",
    max_age=settings.session_max_age,
    same_site="lax",
    https_only=settings.session_cookie_secure,
)

if settings.allowed_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["Content-Type"],
)


def _create_flow(state: str | None = None) -> Flow:
    if not settings.gmail_credentials_path.exists():
        raise FileNotFoundError(
            f"Missing Gmail credentials file: {settings.gmail_credentials_path}"
        )
    return Flow.from_client_secrets_file(
        str(settings.gmail_credentials_path),
        scopes=SCOPES_READONLY,
        redirect_uri=REDIRECT_URI,
        state=state,
    )


def _safe_email(email: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", email.strip())


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]", "_", (name or "").strip())
    return cleaned or "attachment"


def _token_path_for_email(email: str) -> Path:
    return TOKEN_DIR / f"{_safe_email(email)}.json"


def _require_user_email(request: Request) -> str:
    email = request.session.get("user_email")
    if not email:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return email


def _credentials_for_user(email: str) -> OAuth2Credentials | None:
    # Try Supabase first
    if SUPABASE_STORE:
        token_json = SUPABASE_STORE.load_gmail_token(email)
        if token_json:
            try:
                info = json.loads(token_json)
                return OAuth2Credentials.from_authorized_user_info(info, SCOPES_READONLY)
            except Exception:
                logger.exception("Failed to load credentials from Supabase for %s", email)

    # Fallback to local token file
    token_path = _token_path_for_email(email)
    if token_path.exists():
        try:
            creds = OAuth2Credentials.from_authorized_user_file(str(token_path), SCOPES_READONLY)
            return creds
        except Exception:
            logger.exception("Failed to load credentials from file for %s", email)
    return None


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
    )
    response.headers.setdefault("Cache-Control", "no-store")
    response.headers.setdefault("Pragma", "no-cache")
    return response


def _summarize_message(
    message: EmailMessage,
    gemini: Optional[Union[GeminiSummarizer, GroqSummarizer]],
    local: LocalHeuristicSummarizer,
) -> SummaryResult:
    if gemini:
        try:
            return gemini.summarize(message)
        except Exception as exc:  # noqa: BLE001 - surface fallback without failing
            logger.warning("Gemini failed, using local summarizer: %s", exc)
    return local.summarize(message)


def _sanitize_html(html: str) -> str:
    if not html:
        return ""
    allowed_tags = [
        "a",
        "abbr",
        "b",
        "blockquote",
        "br",
        "code",
        "div",
        "em",
        "hr",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "i",
        "img",
        "li",
        "ol",
        "p",
        "pre",
        "style",
        "span",
        "strong",
        "sub",
        "sup",
        "table",
        "tbody",
        "td",
        "th",
        "thead",
        "tr",
        "u",
        "ul",
    ]
    allowed_attrs = {
        "a": ["href", "title", "target", "rel"],
        "img": ["alt", "height", "src", "title", "width", "style"],
        "div": ["style"],
        "span": ["style"],
        "p": ["style"],
        "table": ["border", "cellpadding", "cellspacing", "style"],
        "tbody": ["style"],
        "td": ["colspan", "rowspan", "style"],
        "th": ["colspan", "rowspan", "style"],
        "tr": ["style"],
        "blockquote": ["style"],
        "pre": ["style"],
        "td": ["colspan", "rowspan"],
        "th": ["colspan", "rowspan"],
        "table": ["border", "cellpadding", "cellspacing"],
    }
    css_sanitizer = CSSSanitizer(
        allowed_css_properties=[
            "background",
            "background-color",
            "border",
            "border-bottom",
            "border-collapse",
            "border-left",
            "border-radius",
            "border-right",
            "border-spacing",
            "border-top",
            "box-shadow",
            "color",
            "display",
            "font",
            "font-family",
            "font-size",
            "font-style",
            "font-weight",
            "height",
            "letter-spacing",
            "line-height",
            "margin",
            "margin-bottom",
            "margin-left",
            "margin-right",
            "margin-top",
            "max-width",
            "min-height",
            "min-width",
            "padding",
            "padding-bottom",
            "padding-left",
            "padding-right",
            "padding-top",
            "text-align",
            "text-decoration",
            "vertical-align",
            "white-space",
            "width",
        ]
    )
    return bleach.clean(
        html,
        tags=allowed_tags,
        attributes=allowed_attrs,
        protocols=["http", "https", "mailto", "tel", "cid", "data"],
        css_sanitizer=css_sanitizer,
        strip=True,
        strip_comments=True,
    )


def _verification_from_auth_results(auth_results: str) -> tuple[bool, str]:
    if not auth_results:
        return False, "No authentication results."
    lower = auth_results.lower()
    parts = []
    if "dkim=pass" in lower:
        parts.append("dkim=pass")
    if "spf=pass" in lower:
        parts.append("spf=pass")
    if "dmarc=pass" in lower:
        parts.append("dmarc=pass")
    if parts:
        return True, " ".join(parts)
    return False, auth_results


def _attachment_response(data: bytes, mime_type: str, filename: str) -> Response:
    if not data:
        raise HTTPException(status_code=404, detail="Attachment not found.")
    safe_name = _safe_filename(filename)
    inline_types = ("image/", "application/pdf")
    disposition = (
        "inline" if mime_type.startswith(inline_types) else "attachment"
    )
    headers = {"Content-Disposition": f'{disposition}; filename="{safe_name}"'}
    return Response(content=data, media_type=mime_type, headers=headers)


@app.get("/api/health")
def api_health() -> dict:
    return {"status": "ok"}


@app.get("/api/me")
def api_me(request: Request) -> dict:
    email = _require_user_email(request)
    return {"user": email}


@app.get("/auth/google")
def auth_google(request: Request) -> RedirectResponse:
    flow = _create_flow()
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    request.session["oauth_state"] = state
    request.session["oauth_code_verifier"] = flow.code_verifier
    return RedirectResponse(auth_url)


@app.get("/auth/google/callback")
def auth_google_callback(request: Request) -> RedirectResponse:
    state = request.query_params.get("state")
    code = request.query_params.get("code")
    if not state or not code:
        raise HTTPException(status_code=400, detail="Missing state or code.")

    session_state = request.session.get("oauth_state")
    if not session_state or session_state != state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state.")

    flow = _create_flow(state=state)
    code_verifier = request.session.get("oauth_code_verifier")
    if code_verifier:
        flow.code_verifier = code_verifier

    flow.fetch_token(code=code)
    creds = flow.credentials

    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    email = profile.get("emailAddress")
    if not email:
        raise HTTPException(status_code=500, detail="Could not read user profile.")

    # Persist token to Supabase when available, otherwise fall back to local file
    token_json = creds.to_json()
    if SUPABASE_STORE:
        try:
            SUPABASE_STORE.ensure_user(email, profile.get("emailAddress"))
            SUPABASE_STORE.save_gmail_token(email, token_json)
        except Exception:
            logger.exception("Failed to save token to Supabase for %s", email)
            # fallback to local file
            _token_path_for_email(email).write_text(token_json, encoding="utf-8")
    else:
        _token_path_for_email(email).write_text(token_json, encoding="utf-8")

    request.session["user_email"] = email
    request.session.pop("oauth_state", None)
    request.session.pop("oauth_code_verifier", None)

    return RedirectResponse(f"{FRONTEND_URL}/auth/callback")


@app.get("/auth/logout")
def auth_logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(FRONTEND_URL)


@app.get("/api/messages")
def api_messages(
    request: Request,
    max_results: int = Query(20, ge=1, le=100),
    query: str = Query("", max_length=256),
    ai: bool = False,
) -> dict:
    email = _require_user_email(request)
    creds = _credentials_for_user(email)
    if not creds:
        raise HTTPException(status_code=401, detail="No token for user.")

    client = GmailClient(
        credentials_path=settings.gmail_credentials_path,
        token_path=_token_path_for_email(email),
        scopes=SCOPES_READONLY,
        max_body_chars=settings.max_body_chars,
        credentials=creds,
        persist_token=(lambda t, e=email: SUPABASE_STORE.save_gmail_token(e, t)) if SUPABASE_STORE else None,
    )

    query_parts = ["in:inbox", "category:primary"]
    if query:
        query_parts.append(query)
    gmail_query = " ".join(query_parts).strip()

    messages = client.list_messages(gmail_query, None, max_results)

    ai_summarizer = None
    if ai and settings.groq_api_key:
        ai_summarizer = GroqSummarizer(settings.groq_api_key, settings.groq_model)
    elif ai and settings.gemini_api_key and not settings.disable_gemini:
        ai_summarizer = GeminiSummarizer(
            settings.gemini_api_key, settings.gemini_model
        )
    local = LocalHeuristicSummarizer()

    items = []
    for message in messages:
        summary = _summarize_message(message, ai_summarizer, local)
        sender_verified, verification_detail = _verification_from_auth_results(
            message.auth_results
        )
        safe_html = _sanitize_html(message.body_html)
        items.append(
            {
                "id": message.id,
                "thread_id": message.thread_id,
                "subject": message.subject,
                "from": message.sender,
                "from_name": message.sender_name,
                "from_email": message.sender_email,
                "to": message.to,
                "to_emails": message.to_emails,
                "date": message.date,
                "snippet": message.snippet,
                "body": message.body,
                "body_html": safe_html,
                "labels": message.labels,
                "is_unread": message.is_unread,
                "auth_results": message.auth_results,
                "attachments": [
                    {
                        "attachment_id": attachment.attachment_id,
                        "part_id": attachment.part_id,
                        "filename": attachment.filename,
                        "mime_type": attachment.mime_type,
                        "size": attachment.size,
                        "content_id": attachment.content_id,
                        "is_inline": attachment.is_inline,
                    }
                    for attachment in message.attachments
                ],
                "sender_verified": sender_verified,
                "verification_detail": verification_detail,
                "list_unsubscribe": message.list_unsubscribe,
                "gmail_url": f"https://mail.google.com/mail/u/0/#all/{message.id}",
                "summary": summary.summary,
                "action_items": summary.action_items,
                "concern": summary.concern,
                "classification": summary.classification,
                "legitimacy_reason": summary.legitimacy_reason,
                "why_received": summary.why_received,
                "unsubscribe_instructions": summary.unsubscribe_instructions,
                "topic": summary.topic,
                "provider": summary.provider,
                "what_it_is": summary.what_it_is,
                "main_offer": summary.main_offer,
                "key_benefits": summary.key_benefits,
                "what_it_contains": summary.what_it_contains,
                "how_to_open": summary.how_to_open,
                "important_notes": summary.important_notes,
                "what_you_should_do": summary.what_you_should_do,
            }
        )

    return {"user": email, "count": len(items), "items": items}


@app.get("/api/messages/{message_id}/summary")
def api_message_summary(request: Request, message_id: str) -> dict:
    email = _require_user_email(request)
    creds = _credentials_for_user(email)
    if not creds:
        raise HTTPException(status_code=401, detail="No token for user.")

    client = GmailClient(
        credentials_path=settings.gmail_credentials_path,
        token_path=_token_path_for_email(email),
        scopes=SCOPES_READONLY,
        max_body_chars=settings.max_body_chars,
        credentials=creds,
        persist_token=(lambda t, e=email: SUPABASE_STORE.save_gmail_token(e, t)) if SUPABASE_STORE else None,
    )
    message = client.get_message(message_id)

    if not settings.groq_api_key:
        raise HTTPException(status_code=503, detail="Groq API key not configured.")

    # Try cached summary from Supabase
    if SUPABASE_STORE:
        try:
            cached = SUPABASE_STORE.load_message_summary(email, message_id)
            if cached:
                return cached
        except Exception:
            logger.exception("Failed to load cached summary for %s", message_id)

    summarizer = GroqSummarizer(settings.groq_api_key, settings.groq_model)
    try:
        summary = summarizer.summarize(message)
    except Exception as exc:  # noqa: BLE001 - surface upstream failure
        logger.warning("Groq summarizer failed: %s", exc)
        raise HTTPException(
            status_code=502, detail="Groq summarization failed. Try again."
        )

    # Persist summary to Supabase cache when available
    if SUPABASE_STORE:
        try:
            SUPABASE_STORE.save_message_summary(email, message_id, {
                "summary": summary.summary,
                "action_items": summary.action_items,
                "concern": summary.concern,
                "classification": summary.classification,
                "legitimacy_reason": summary.legitimacy_reason,
                "why_received": summary.why_received,
                "unsubscribe_instructions": summary.unsubscribe_instructions,
                "topic": summary.topic,
                "provider": summary.provider,
                "what_it_is": summary.what_it_is,
                "main_offer": summary.main_offer,
                "key_benefits": summary.key_benefits,
                "what_it_contains": summary.what_it_contains,
                "how_to_open": summary.how_to_open,
                "important_notes": summary.important_notes,
                "what_you_should_do": summary.what_you_should_do,
            })
        except Exception:
            logger.exception("Failed to save message summary for %s", message_id)

    return {
        "summary": summary.summary,
        "action_items": summary.action_items,
        "concern": summary.concern,
        "classification": summary.classification,
        "legitimacy_reason": summary.legitimacy_reason,
        "why_received": summary.why_received,
        "unsubscribe_instructions": summary.unsubscribe_instructions,
        "topic": summary.topic,
        "provider": summary.provider,
        "what_it_is": summary.what_it_is,
        "main_offer": summary.main_offer,
        "key_benefits": summary.key_benefits,
        "what_it_contains": summary.what_it_contains,
        "how_to_open": summary.how_to_open,
        "important_notes": summary.important_notes,
        "what_you_should_do": summary.what_you_should_do,
    }


@app.get("/api/messages/{message_id}/attachments/{attachment_id}")
def api_attachment(
    request: Request, message_id: str, attachment_id: str
) -> Response:
    email = _require_user_email(request)
    creds = _credentials_for_user(email)
    if not creds:
        raise HTTPException(status_code=401, detail="No token for user.")

    client = GmailClient(
        credentials_path=settings.gmail_credentials_path,
        token_path=_token_path_for_email(email),
        scopes=SCOPES_READONLY,
        max_body_chars=settings.max_body_chars,
        credentials=creds,
        persist_token=(lambda t, e=email: SUPABASE_STORE.save_gmail_token(e, t)) if SUPABASE_STORE else None,
    )
    data, mime_type, filename = client.get_attachment_by_id(
        message_id, attachment_id
    )
    return _attachment_response(data, mime_type, filename)


@app.get("/api/messages/{message_id}/attachments/part/{part_id}")
def api_attachment_part(
    request: Request, message_id: str, part_id: str
) -> Response:
    email = _require_user_email(request)
    creds = _credentials_for_user(email)
    if not creds:
        raise HTTPException(status_code=401, detail="No token for user.")

    client = GmailClient(
        credentials_path=settings.gmail_credentials_path,
        token_path=_token_path_for_email(email),
        scopes=SCOPES_READONLY,
        max_body_chars=settings.max_body_chars,
        credentials=creds,
        persist_token=(lambda t, e=email: SUPABASE_STORE.save_gmail_token(e, t)) if SUPABASE_STORE else None,
    )
    data, mime_type, filename = client.get_attachment_by_part_id(message_id, part_id)
    return _attachment_response(data, mime_type, filename)