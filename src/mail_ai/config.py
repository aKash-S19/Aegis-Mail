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
    supabase_url: str | None
    supabase_service_role_key: str | None
    supabase_anon_key: str | None
    token_encryption_key: str | None
    gmail_credentials_path: Path
    gmail_token_path: Path
    output_dir: Path
    max_body_chars: int


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
        supabase_url=os.getenv("SUPABASE_URL") or None,
        supabase_service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY") or None,
        supabase_anon_key=os.getenv("SUPABASE_ANON_KEY") or None,
        token_encryption_key=os.getenv("TOKEN_ENCRYPTION_KEY") or None,
        gmail_credentials_path=Path(
            os.getenv("GMAIL_CREDENTIALS_PATH", "credentials.json")
        ),
        gmail_token_path=Path(os.getenv("GMAIL_TOKEN_PATH", "token.json")),
        output_dir=Path(os.getenv("OUTPUT_DIR", "outputs")),
        max_body_chars=int(os.getenv("MAX_BODY_CHARS", "6000")),
    )
