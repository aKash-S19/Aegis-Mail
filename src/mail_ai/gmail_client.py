from __future__ import annotations

from pathlib import Path
import base64
from email.utils import getaddresses, parseaddr
import re
from typing import Callable, Iterable, List, Optional
import logging

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .models import AttachmentInfo, EmailMessage


SCOPES_READONLY = ["https://www.googleapis.com/auth/gmail.readonly"]


def _decode_base64_bytes(data: str) -> bytes:
    if not data:
        return b""
    padding = (4 - len(data) % 4) % 4
    if padding:
        data += "=" * padding
    return base64.urlsafe_b64decode(data.encode("utf-8"))


def _decode_base64(data: str) -> str:
    return _decode_base64_bytes(data).decode("utf-8", errors="replace")


def _strip_html(text: str) -> str:
    text = re.sub(
        r"<\s*(script|style)[^>]*>.*?<\s*/\1\s*>",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(r"<\s*br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def _collect_parts(payload: dict) -> tuple[list[str], list[str]]:
    plain_parts: list[str] = []
    html_parts: list[str] = []

    def walk(part: dict) -> None:
        mime_type = part.get("mimeType", "")
        body = part.get("body", {})
        data = body.get("data")
        if data:
            decoded = _decode_base64(data)
            if mime_type.startswith("text/plain"):
                plain_parts.append(decoded)
            elif mime_type.startswith("text/html"):
                html_parts.append(decoded)
        for child in part.get("parts", []):
            walk(child)

    walk(payload)
    return plain_parts, html_parts


def _extract_bodies(payload: dict) -> tuple[str, str]:
    plain_parts, html_parts = _collect_parts(payload)
    plain_text = "\n".join(plain_parts).strip()
    html_text = "\n".join(html_parts).strip()
    if not plain_text and html_text:
        plain_text = _strip_html(html_text)
    return plain_text, html_text


def _get_header(headers: Iterable[dict], name: str) -> str:
    name = name.lower()
    for header in headers:
        if header.get("name", "").lower() == name:
            return header.get("value", "")
    return ""


def _truncate(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return text
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _parse_list_unsubscribe(value: str) -> list[str]:
    if not value:
        return []
    items = [part.strip() for part in value.split(",") if part.strip()]
    results: list[str] = []
    for item in items:
        matches = re.findall(r"<([^>]+)>", item)
        if matches:
            results.extend(matches)
        else:
            results.append(item)
    seen = set()
    cleaned = []
    for item in results:
        item = item.strip()
        if item and item not in seen:
            cleaned.append(item)
            seen.add(item)
    return cleaned


def _find_part(payload: dict, predicate) -> Optional[dict]:
    if predicate(payload):
        return payload
    for child in payload.get("parts", []):
        found = _find_part(child, predicate)
        if found:
            return found
    return None


def _collect_attachments(payload: dict) -> list[AttachmentInfo]:
    attachments: list[AttachmentInfo] = []

    def walk(part: dict) -> None:
        mime_type = part.get("mimeType", "")
        filename = part.get("filename", "")
        body = part.get("body", {})
        attachment_id = body.get("attachmentId", "") or ""
        size = body.get("size") or 0
        headers = part.get("headers", [])
        content_id = _get_header(headers, "Content-ID").strip()
        if content_id.startswith("<") and content_id.endswith(">"):
            content_id = content_id[1:-1]
        disposition = _get_header(headers, "Content-Disposition").lower()
        is_inline = "inline" in disposition

        is_text = mime_type.startswith("text/")
        has_attachment = bool(filename) or bool(attachment_id) or bool(content_id)
        if has_attachment and not (is_text and not filename and not attachment_id):
            attachments.append(
                AttachmentInfo(
                    attachment_id=attachment_id,
                    part_id=part.get("partId", ""),
                    filename=filename or content_id or "attachment",
                    mime_type=mime_type or "application/octet-stream",
                    size=int(size or 0),
                    content_id=content_id,
                    is_inline=is_inline,
                )
            )

        for child in part.get("parts", []):
            walk(child)

    walk(payload)
    return attachments


class GmailClient:
    def __init__(
        self,
        credentials_path: Path,
        token_path: Path,
        scopes: List[str],
        max_body_chars: int = 6000,
        credentials: Credentials | None = None,
        persist_token: Callable[[str], None] | None = None,
    ):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.scopes = scopes
        self.max_body_chars = max_body_chars
        self._provided_credentials = credentials
        self._persist_token_cb = persist_token
        self._logger = logging.getLogger("mail_ai.gmail_client")
        self.service = build("gmail", "v1", credentials=self._get_credentials())

    def _get_credentials(self) -> Credentials:
        if self._provided_credentials:
            return self._provided_credentials
        creds: Optional[Credentials] = None
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(
                str(self.token_path), self.scopes
            )
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                # Persist refreshed token
                try:
                    token_json = creds.to_json()
                    if self._persist_token_cb:
                        try:
                            self._persist_token_cb(token_json)
                        except Exception:
                            self._logger.exception("persist_token callback failed")
                    else:
                        self.token_path.write_text(token_json, encoding="utf-8")
                except Exception:
                    self._logger.exception("Failed to persist refreshed credentials")
            else:
                if not self.credentials_path.exists():
                    raise FileNotFoundError(
                        f"Missing Gmail credentials file: {self.credentials_path}"
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path), self.scopes
                )
                creds = flow.run_local_server(port=0)
            try:
                token_json = creds.to_json()
                if self._persist_token_cb:
                    try:
                        self._persist_token_cb(token_json)
                    except Exception:
                        self._logger.exception("persist_token callback failed")
                        self.token_path.write_text(token_json, encoding="utf-8")
                else:
                    self.token_path.write_text(token_json, encoding="utf-8")
            except Exception:
                self._logger.exception("Failed to persist credentials to file")
        return creds

    def list_messages(
        self, query: str, label_ids: Optional[List[str]], max_results: int
    ) -> List[EmailMessage]:
        response = (
            self.service.users()
            .messages()
            .list(userId="me", q=query, labelIds=label_ids, maxResults=max_results)
            .execute()
        )
        messages = response.get("messages", [])
        results: List[EmailMessage] = []
        for item in messages:
            message = self._get_message(item["id"])
            results.append(message)
        return results

    def get_message(self, message_id: str) -> EmailMessage:
        return self._get_message(message_id)

    def _get_message(self, message_id: str) -> EmailMessage:
        raw = (
            self.service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        payload = raw.get("payload", {})
        headers = payload.get("headers", [])
        labels = raw.get("labelIds", [])
        plain_body, html_body = _extract_bodies(payload)
        body = _truncate(plain_body, self.max_body_chars)
        body_html = html_body
        sender_header = _get_header(headers, "From")
        sender_name, sender_email = parseaddr(sender_header)
        to_header = _get_header(headers, "To")
        to_emails = [addr for _, addr in getaddresses([to_header]) if addr]
        list_unsubscribe = _parse_list_unsubscribe(
            _get_header(headers, "List-Unsubscribe")
        )
        auth_results = _get_header(headers, "Authentication-Results")
        attachments = _collect_attachments(payload)

        return EmailMessage(
            id=raw.get("id", ""),
            thread_id=raw.get("threadId", ""),
            subject=_get_header(headers, "Subject") or "(no subject)",
            sender=sender_header,
            sender_name=sender_name,
            sender_email=sender_email,
            to=to_header,
            to_emails=to_emails,
            date=_get_header(headers, "Date"),
            snippet=raw.get("snippet", ""),
            body=body,
            body_html=body_html,
            labels=labels,
            is_unread="UNREAD" in labels,
            list_unsubscribe=list_unsubscribe,
            auth_results=auth_results,
            attachments=attachments,
        )

    def get_attachment_by_id(
        self, message_id: str, attachment_id: str
    ) -> tuple[bytes, str, str]:
        raw = (
            self.service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        payload = raw.get("payload", {})
        part = _find_part(
            payload,
            lambda item: item.get("body", {}).get("attachmentId") == attachment_id,
        )
        filename = (part or {}).get("filename") or "attachment"
        mime_type = (part or {}).get("mimeType") or "application/octet-stream"
        attachment = (
            self.service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=attachment_id)
            .execute()
        )
        data = _decode_base64_bytes(attachment.get("data", ""))
        return data, mime_type, filename

    def get_attachment_by_part_id(
        self, message_id: str, part_id: str
    ) -> tuple[bytes, str, str]:
        raw = (
            self.service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        payload = raw.get("payload", {})
        part = _find_part(payload, lambda item: item.get("partId") == part_id)
        if not part:
            return b"", "application/octet-stream", "attachment"
        body = part.get("body", {})
        data = _decode_base64_bytes(body.get("data", ""))
        filename = part.get("filename") or "attachment"
        mime_type = part.get("mimeType") or "application/octet-stream"
        return data, mime_type, filename
