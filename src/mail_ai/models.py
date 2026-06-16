from __future__ import annotations

from dataclasses import dataclass, field
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
    topic: str
    provider: str
    category: str = "informational"
    concern: str = ""
    classification: str = "unknown"
    legitimacy_reason: str = ""
    why_received: str = ""
    unsubscribe_instructions: str = ""
    what_it_is: str = ""
    main_offer: str = ""
    key_benefits: List[str] = field(default_factory=list)
    what_it_contains: List[str] = field(default_factory=list)
    how_to_open: str = ""
    important_notes: List[str] = field(default_factory=list)
    what_you_should_do: List[str] = field(default_factory=list)
    sender_intent: str = ""
    terms_explained: List[str] = field(default_factory=list)
