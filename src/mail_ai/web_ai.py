from __future__ import annotations

import logging
import os
import re
import secrets
from pathlib import Path
from itsdangerous import URLSafeTimedSerializer
from typing import Optional, Union

import bleach
from bleach.css_sanitizer import CSSSanitizer
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
import json

from google.oauth2.credentials import Credentials as OAuth2Credentials

from .firebase_store import FirebaseStore, FirebaseConfig

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from .config import load_settings
from .gmail_client import GmailClient, SCOPES_READONLY
from .summarize import GeminiSummarizer, GroqSummarizer, LocalHeuristicSummarizer
from .models import EmailMessage, SummaryResult


settings = load_settings()
logger = logging.getLogger("mail_ai.web")
FRONTEND_URL = settings.web_frontend_url
ALLOWED_ORIGINS = list(
    dict.fromkeys(
        [
            FRONTEND_URL,
            "http://localhost:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:5174",
            "https://aiaegismail.vercel.app",
        ]
    )
)
logger.info("CORS allowed origins: %s", ALLOWED_ORIGINS)
REDIRECT_URI = os.getenv(
    "WEB_REDIRECT_URI", "http://localhost:8000/auth/google/callback"
)
TOKEN_DIR = Path(os.getenv("TOKEN_DIR", "tokens"))
TOKEN_DIR.mkdir(parents=True, exist_ok=True)

# Initialize Firebase Admin SDK + store when configured
FIREBASE_STORE: FirebaseStore | None = None
_firebase_auth = None
_is_placeholder = lambda v: v and v.strip().startswith("your-")
firebase_available = (
    settings.firebase_project_id
    and settings.firebase_private_key
    and settings.firebase_client_email
    and not _is_placeholder(settings.firebase_project_id)
    and not _is_placeholder(settings.firebase_client_email)
)
if firebase_available:
    try:
        import firebase_admin
        from firebase_admin import auth as firebase_auth, credentials as fb_creds

        _firebase_app = firebase_admin.initialize_app(
            fb_creds.Certificate({
                "type": "service_account",
                "project_id": settings.firebase_project_id,
                "private_key": settings.firebase_private_key.replace("\\n", "\n"),
                "client_email": settings.firebase_client_email,
                "token_uri": "https://oauth2.googleapis.com/token",
            })
        )
        _firebase_auth = firebase_auth
        FIREBASE_STORE = FirebaseStore(
            FirebaseConfig(
                project_id=settings.firebase_project_id,
                private_key=settings.firebase_private_key.replace("\\n", "\n"),
                client_email=settings.firebase_client_email,
                token_encryption_key=os.getenv("TOKEN_ENCRYPTION_KEY") or None,
            ),
            app=_firebase_app,
        )
    except Exception:
        logger.exception("Failed to initialize Firebase Admin SDK")
        _firebase_auth = None
else:
    _firebase_auth = None

app = FastAPI(title="Aegis Mail", version="0.1.0")

session_secret = settings.session_secret or secrets.token_urlsafe(48)
if not settings.session_secret:
    logger.warning("SESSION_SECRET is not set; using a temporary in-memory secret.")

state_serializer = URLSafeTimedSerializer(
    secret_key=session_secret,
    salt="aegis-oauth-state",
)

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
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


class FirebaseAuthRequest(BaseModel):
    id_token: str


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
    if email:
        return email

    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer ") and _firebase_auth:
        token = auth[7:]
        try:
            decoded = _firebase_auth.verify_id_token(token)
            decoded_email = decoded.get("email", "")
            if decoded_email:
                uid = decoded.get("uid", "")
                request.session["firebase_uid"] = uid
                request.session["user_email"] = decoded_email
                return decoded_email
        except Exception:
            logger.warning("Invalid Bearer token")

    raise HTTPException(status_code=401, detail="Not authenticated.")


def _get_user_id(request: Request) -> str:
    uid = request.session.get("firebase_uid") or request.session.get("user_email", "")
    return uid


def _persist_token(uid: str) -> callable:
    def persist(token_json: str) -> None:
        if not FIREBASE_STORE:
            return
        try:
            FIREBASE_STORE.save_gmail_token(uid, token_json)
        except Exception:
            logger.warning("Failed to persist token to Firestore for %s", uid)
    return persist


def _credentials_for_user(email: str, uid: str = "") -> OAuth2Credentials | None:
    if not uid:
        uid = email
    if FIREBASE_STORE:
        try:
            token_json = FIREBASE_STORE.load_gmail_token(uid)
            if token_json:
                try:
                    info = json.loads(token_json)
                    return OAuth2Credentials.from_authorized_user_info(info, SCOPES_READONLY)
                except Exception:
                    logger.exception("Failed to load credentials from Firestore for %s", email)
        except Exception:
            logger.warning("Firestore unavailable, falling back to local file for %s", email)

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
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if FRONTEND_URL.startswith("https://"):
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def _summarize_message(
    message: EmailMessage,
    gemini: Optional[Union[GeminiSummarizer, GroqSummarizer]],
    local: LocalHeuristicSummarizer,
) -> SummaryResult:
    if gemini:
        try:
            return gemini.summarize(message)
        except Exception as exc:
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


@app.post("/api/auth/firebase")
def api_auth_firebase(request: Request, body: FirebaseAuthRequest) -> dict:
    if not _firebase_auth:
        raise HTTPException(status_code=503, detail="Firebase Auth not configured.")
    try:
        decoded = _firebase_auth.verify_id_token(body.id_token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")

    uid = decoded.get("uid", "")
    email = decoded.get("email", "")
    name = decoded.get("name", "")

    if not email:
        raise HTTPException(status_code=400, detail="No email in Firebase token.")

    if FIREBASE_STORE:
        try:
            FIREBASE_STORE.ensure_user(uid, email, name)
        except Exception:
            logger.exception("Failed to create user in Firestore")

    request.session["firebase_uid"] = uid
    request.session["user_email"] = email
    return {"user": email, "uid": uid}


@app.get("/auth/google")
def auth_google(request: Request) -> RedirectResponse:
    email = _require_user_email(request)
    uid = _get_user_id(request)
    flow = _create_flow()
    signed_state = state_serializer.dumps({
        "code_verifier": flow.code_verifier,
        "uid": uid,
    })
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=signed_state,
    )
    return RedirectResponse(auth_url)


@app.get("/api/auth/gmail-url")
def api_gmail_auth_url(request: Request) -> dict:
    email = _require_user_email(request)
    uid = _get_user_id(request)
    flow = _create_flow()
    signed_state = state_serializer.dumps({
        "code_verifier": flow.code_verifier,
        "uid": uid,
    })
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=signed_state,
    )
    return {"url": auth_url}


@app.get("/auth/google/callback")
def auth_google_callback(request: Request) -> RedirectResponse:
    raw_state = request.query_params.get("state")
    code = request.query_params.get("code")
    if not raw_state or not code:
        raise HTTPException(status_code=400, detail="Missing state or code.")

    try:
        payload = state_serializer.loads(raw_state, max_age=600)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state.")

    uid = payload.get("uid", "")
    code_verifier = payload.get("code_verifier")

    flow = _create_flow(state=raw_state)
    if code_verifier:
        flow.code_verifier = code_verifier

    flow.fetch_token(code=code)
    creds = flow.credentials

    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    email = profile.get("emailAddress")
    if not email:
        raise HTTPException(status_code=500, detail="Could not read user profile.")

    token_json = creds.to_json()
    if FIREBASE_STORE:
        try:
            FIREBASE_STORE.save_gmail_token(uid, token_json)
        except Exception:
            logger.exception("Failed to save token to Firestore for %s", email)
            _token_path_for_email(email).write_text(token_json, encoding="utf-8")
    else:
        _token_path_for_email(email).write_text(token_json, encoding="utf-8")

    request.session["firebase_uid"] = uid
    request.session["user_email"] = email

    return RedirectResponse(f"{FRONTEND_URL}/auth/callback")


@app.get("/auth/logout")
def auth_logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(FRONTEND_URL)


def _revoke_google_token(token_json: str) -> None:
    try:
        info = json.loads(token_json)
        token = info.get("access_token") or info.get("token") or ""
        if token:
            import urllib.request
            req = urllib.request.Request(
                "https://oauth2.googleapis.com/revoke",
                data=f"token={token}".encode(),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            urllib.request.urlopen(req)
    except Exception:
        logger.warning("Failed to revoke Google token")


@app.post("/api/auth/delete-account")
def api_delete_account(request: Request) -> dict:
    email = _require_user_email(request)
    uid = _get_user_id(request)

    if FIREBASE_STORE:
        try:
            token_json = FIREBASE_STORE.load_gmail_token(uid)
            if token_json:
                _revoke_google_token(token_json)
            FIREBASE_STORE.delete_user_data(uid)
        except Exception:
            logger.exception("Failed to delete user data from Firestore")

    token_path = _token_path_for_email(email)
    if token_path.exists():
        try:
            token_path.unlink()
        except Exception:
            logger.warning("Failed to delete local token file for %s", email)

    request.session.clear()
    logger.info("Account deleted for %s (uid=%s)", email, uid)
    return {"status": "ok"}


@app.get("/api/messages")
def api_messages(
    request: Request,
    max_results: int = Query(20, ge=1, le=100),
    query: str = Query("", max_length=256),
    ai: bool = False,
) -> dict:
    email = _require_user_email(request)
    uid = _get_user_id(request)
    creds = _credentials_for_user(email, uid)
    if not creds:
        raise HTTPException(status_code=401, detail="No token for user.")

    client = GmailClient(
        credentials_path=settings.gmail_credentials_path,
        token_path=_token_path_for_email(email),
        scopes=SCOPES_READONLY,
        max_body_chars=settings.max_body_chars,
        credentials=creds,
        persist_token=_persist_token(uid),
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
    uid = _get_user_id(request)
    creds = _credentials_for_user(email, uid)
    if not creds:
        raise HTTPException(status_code=401, detail="No token for user.")

    client = GmailClient(
        credentials_path=settings.gmail_credentials_path,
        token_path=_token_path_for_email(email),
        scopes=SCOPES_READONLY,
        max_body_chars=settings.max_body_chars,
        credentials=creds,
        persist_token=_persist_token(uid),
    )
    message = client.get_message(message_id)

    if FIREBASE_STORE:
        try:
            cached = FIREBASE_STORE.load_message_summary(uid, message_id)
            if cached:
                return cached
        except Exception:
            logger.exception("Failed to load cached summary for %s", message_id)

    ai_summarizer = None
    if settings.groq_api_key:
        ai_summarizer = GroqSummarizer(settings.groq_api_key, settings.groq_model)
    elif settings.gemini_api_key and not settings.disable_gemini:
        ai_summarizer = GeminiSummarizer(
            settings.gemini_api_key, settings.gemini_model
        )
    local = LocalHeuristicSummarizer()

    summary = _summarize_message(message, ai_summarizer, local)

    if FIREBASE_STORE:
        try:
            FIREBASE_STORE.save_message_summary(uid, message_id, {
                "summary": summary.summary,
                "action_items": summary.action_items,
                "topic": summary.topic,
                "provider": summary.provider,
                "category": summary.category,
            })
        except Exception:
            logger.exception("Failed to save message summary for %s", message_id)

    return {
        "summary": summary.summary,
        "action_items": summary.action_items,
        "topic": summary.topic,
        "provider": summary.provider,
        "category": summary.category,
    }


@app.get("/api/messages/{message_id}/attachments/{attachment_id}")
def api_attachment(
    request: Request, message_id: str, attachment_id: str
) -> Response:
    email = _require_user_email(request)
    uid = _get_user_id(request)
    creds = _credentials_for_user(email, uid)
    if not creds:
        raise HTTPException(status_code=401, detail="No token for user.")

    client = GmailClient(
        credentials_path=settings.gmail_credentials_path,
        token_path=_token_path_for_email(email),
        scopes=SCOPES_READONLY,
        max_body_chars=settings.max_body_chars,
        credentials=creds,
        persist_token=_persist_token(uid),
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
    uid = _get_user_id(request)
    creds = _credentials_for_user(email, uid)
    if not creds:
        raise HTTPException(status_code=401, detail="No token for user.")

    client = GmailClient(
        credentials_path=settings.gmail_credentials_path,
        token_path=_token_path_for_email(email),
        scopes=SCOPES_READONLY,
        max_body_chars=settings.max_body_chars,
        credentials=creds,
        persist_token=_persist_token(uid),
    )
    data, mime_type, filename = client.get_attachment_by_part_id(message_id, part_id)
    return _attachment_response(data, mime_type, filename)
