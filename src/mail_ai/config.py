from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None
    gemini_model: str
    groq_api_key: str | None
    groq_model: str
    disable_gemini: bool
    session_secret: str
    session_cookie_secure: bool
    allowed_hosts: list[str]
    session_max_age: int
    gmail_credentials_path: Path
    gmail_token_path: Path
    output_dir: Path
    max_body_chars: int
    firebase_project_id: str | None
    firebase_private_key: str | None
    firebase_client_email: str | None
    firebase_api_key: str | None
    firebase_auth_domain: str | None


def load_settings() -> Settings:
    load_dotenv()

    disable_gemini = os.getenv("DISABLE_GEMINI", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    return Settings(
        gemini_api_key=None if disable_gemini else os.getenv("GEMINI_API_KEY") or None,
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-1.5-flash-001"),
        groq_api_key=os.getenv("GROQ_API_KEY") or None,
        groq_model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        disable_gemini=disable_gemini,
        session_secret=os.getenv("SESSION_SECRET") or "",
        session_cookie_secure=os.getenv("SESSION_COOKIE_SECURE", "false")
        .strip()
        .lower()
        in {"1", "true", "yes", "on"},
        allowed_hosts=[
            host.strip()
            for host in os.getenv(
                "ALLOWED_HOSTS", "localhost,127.0.0.1"
            ).split(",")
            if host.strip()
        ],
        session_max_age=int(os.getenv("SESSION_MAX_AGE", "604800")),
        gmail_credentials_path=Path(
            os.getenv("GMAIL_CREDENTIALS_PATH", "credentials.json")
        ),
        gmail_token_path=Path(os.getenv("GMAIL_TOKEN_PATH", "token.json")),
        output_dir=Path(os.getenv("OUTPUT_DIR", "outputs")),
        max_body_chars=int(os.getenv("MAX_BODY_CHARS", "6000")),
        firebase_project_id=os.getenv("FIREBASE_PROJECT_ID") or None,
        firebase_private_key=os.getenv("FIREBASE_PRIVATE_KEY") or None,
        firebase_client_email=os.getenv("FIREBASE_CLIENT_EMAIL") or None,
        firebase_api_key=os.getenv("FIREBASE_API_KEY") or None,
        firebase_auth_domain=os.getenv("FIREBASE_AUTH_DOMAIN") or None,
    )
