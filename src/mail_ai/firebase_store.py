from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from typing import Any

from cryptography.fernet import Fernet
from firebase_admin import firestore


@dataclass(frozen=True)
class FirebaseConfig:
    project_id: str
    private_key: str
    client_email: str
    token_encryption_key: str | None = None


def _derive_fernet_key(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


class FirebaseStore:
    def __init__(self, config: FirebaseConfig, app=None):
        self._app = app
        self._db = firestore.client(app=self._app)
        encryption_secret = config.token_encryption_key or config.private_key or config.project_id
        self._fernet = Fernet(_derive_fernet_key(encryption_secret))

    def ensure_user(self, uid: str, email: str, display_name: str | None = None) -> None:
        doc_ref = self._db.collection("users").document(uid)
        doc_ref.set({
            "email": email,
            "display_name": display_name or email,
        }, merge=True)

    def save_gmail_token(self, uid: str, token_json: str) -> None:
        encrypted = self._fernet.encrypt(token_json.encode("utf-8")).decode("utf-8")
        doc_ref = self._db.collection("gmail_tokens").document(uid)
        doc_ref.set({
            "uid": uid,
            "token_json_encrypted": encrypted,
        })

    def load_gmail_token(self, uid: str) -> str | None:
        doc_ref = self._db.collection("gmail_tokens").document(uid)
        doc = doc_ref.get()
        if not doc.exists:
            return None
        encrypted = doc.to_dict().get("token_json_encrypted")
        if not encrypted:
            return None
        return self._fernet.decrypt(encrypted.encode("utf-8")).decode("utf-8")

    def save_message_summary(self, uid: str, message_id: str, summary_json: dict) -> None:
        doc_id = f"{uid}_{message_id}"
        doc_ref = self._db.collection("message_summaries").document(doc_id)
        doc_ref.set({
            "uid": uid,
            "message_id": message_id,
            "summary_json": summary_json,
        })

    def load_message_summary(self, uid: str, message_id: str) -> dict | None:
        doc_id = f"{uid}_{message_id}"
        doc_ref = self._db.collection("message_summaries").document(doc_id)
        doc = doc_ref.get()
        if not doc.exists:
            return None
        return doc.to_dict().get("summary_json")

    def delete_user_data(self, uid: str) -> None:
        self._db.collection("users").document(uid).delete()
        self._db.collection("gmail_tokens").document(uid).delete()
        summaries = self._db.collection("message_summaries").where("uid", "==", uid).stream()
        for doc in summaries:
            doc.reference.delete()
