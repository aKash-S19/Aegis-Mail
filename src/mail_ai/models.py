from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class AttachmentInfo:
    attachment_id: str
    part_id: str
    filename: str
    mime_type: str
    size: int
    content_id: str
    is_inline: bool


@dataclass
class EmailMessage:
    id: str
    thread_id: str
    subject: str
    sender: str
    sender_name: str
    sender_email: str
    to: str
    to_emails: List[str]
    date: str
    snippet: str
    body: str
    body_html: str
    labels: List[str]
    is_unread: bool
    list_unsubscribe: List[str]
    auth_results: str
    attachments: List[AttachmentInfo]


@dataclass
class SummaryResult:
    summary: str
    action_items: List[str]
    concern: str
    classification: str
    legitimacy_reason: str
    why_received: str
    unsubscribe_instructions: str
    topic: str
    provider: str
    what_it_is: str
    main_offer: str
    key_benefits: List[str]
    what_it_contains: List[str]
    how_to_open: str
    important_notes: List[str]
    what_you_should_do: List[str]
