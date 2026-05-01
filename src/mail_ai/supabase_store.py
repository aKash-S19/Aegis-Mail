from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Any

import requests
from cryptography.fernet import Fernet


@dataclass(frozen=True)
class SupabaseConfig:
    url: str
    service_role_key: str
    token_encryption_key: str | None = None


def _derive_fernet_key(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


class SupabaseStore:
    def __init__(self, config: SupabaseConfig):
        self.config = config
        self._session = requests.Session()
        self._session.headers.update(
            {
                "apikey": config.service_role_key,
                "Authorization": f"Bearer {config.service_role_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )
        encryption_secret = config.token_encryption_key or config.service_role_key
        self._fernet = Fernet(_derive_fernet_key(encryption_secret))

    def _url(self, path: str) -> str:
        return f"{self.config.url.rstrip('/')}/rest/v1/{path.lstrip('/')}"

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        response = self._session.request(method, self._url(path), timeout=20, **kwargs)
        response.raise_for_status()
        return response

    def ensure_user(self, email: str, display_name: str | None = None) -> dict:
        payload = {
            "email": email,
            "display_name": display_name or email,
        }
        response = self._request(
            "post",
            "app_users?on_conflict=email",
            headers={"Prefer": "resolution=merge-duplicates,return=representation"},
            json=[payload],
        )
        rows = response.json()
        return rows[0] if rows else payload

    def save_gmail_token(self, email: str, token_json: str) -> None:
        encrypted = self._fernet.encrypt(token_json.encode("utf-8")).decode("utf-8")
        payload = {
            "email": email,
            "provider": "google",
            "token_json_encrypted": encrypted,
        }
        self._request(
            "post",
            "gmail_tokens?on_conflict=email,provider",
            headers={"Prefer": "resolution=merge-duplicates"},
            json=[payload],
        )

    def load_gmail_token(self, email: str) -> str | None:
        response = self._request(
            "get",
            "gmail_tokens",
            params={
                "select": "token_json_encrypted",
                "email": f"eq.{email}",
                "provider": "eq.google",
                "limit": 1,
            },
        )
        rows = response.json()
        if not rows:
            return None
        encrypted = rows[0].get("token_json_encrypted")
        if not encrypted:
            return None
        return self._fernet.decrypt(encrypted.encode("utf-8")).decode("utf-8")

    def save_message_summary(self, email: str, message_id: str, summary_json: dict) -> None:
        payload = {
            "email": email,
            "message_id": message_id,
            "summary_json": summary_json,
        }
        self._request(
            "post",
            "message_summaries?on_conflict=email,message_id",
            headers={"Prefer": "resolution=merge-duplicates"},
            json=[payload],
        )

    def load_message_summary(self, email: str, message_id: str) -> dict | None:
        response = self._request(
            "get",
            "message_summaries",
            params={
                "select": "summary_json",
                "email": f"eq.{email}",
                "message_id": f"eq.{message_id}",
                "limit": 1,
            },
        )
        rows = response.json()
        if not rows:
            return None
        return rows[0].get("summary_json")
