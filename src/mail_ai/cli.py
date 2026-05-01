from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
import sys
from typing import List, Optional, Union

from rich.console import Console
from rich.table import Table

from .config import load_settings
from .gmail_client import GmailClient, SCOPES_READONLY
from .models import EmailMessage, SummaryResult
from .summarize import GeminiSummarizer, GroqSummarizer, LocalHeuristicSummarizer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Summarize Gmail messages with AI and export results."
    )
    parser.add_argument("--max", type=int, default=20, help="Max messages to fetch.")
    parser.add_argument(
        "--include-read",
        action="store_true",
        help="Include read messages (default is unread only).",
    )
    parser.add_argument(
        "--query",
        type=str,
        default="",
        help="Additional Gmail search query.",
    )
    parser.add_argument(
        "--labels",
        type=str,
        default="",
        help="Comma-separated Gmail label IDs to filter.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Output directory for JSON export.",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Write JSON only (no table output).",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Skip AI and use only Gmail snippets.",
    )
    parser.add_argument(
        "--local-ai",
        action="store_true",
        help="Force local heuristic summarizer.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings()

    output_dir = Path(args.output) if args.output else settings.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    query_parts = []
    if not args.include_read:
        query_parts.append("is:unread")
    if args.query:
        query_parts.append(args.query)
    query = " ".join(query_parts).strip()

    label_ids = [label.strip() for label in args.labels.split(",") if label.strip()]
    if not label_ids:
        label_ids = None

    try:
        client = GmailClient(
            credentials_path=settings.gmail_credentials_path,
            token_path=settings.gmail_token_path,
            scopes=SCOPES_READONLY,
            max_body_chars=settings.max_body_chars,
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    messages = client.list_messages(query, label_ids, args.max)
    if not messages:
        print("No messages found.")
        return 0

    gemini = None
    groq = None
    local = LocalHeuristicSummarizer()
    if not args.no_ai and not args.local_ai:
        if settings.groq_api_key:
            groq = GroqSummarizer(settings.groq_api_key, settings.groq_model)
        elif settings.gemini_api_key and not settings.disable_gemini:
            gemini = GeminiSummarizer(settings.gemini_api_key, settings.gemini_model)

    results = []
    for message in messages:
        summary = summarize_message(message, groq or gemini, local, args.no_ai)
        results.append(_export_record(message, summary))

    output_path = output_dir / _export_filename()
    output_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    if not args.json_only:
        _render_table(results)

    print(f"Wrote {len(results)} summaries to {output_path}")
    return 0


def summarize_message(
    message: EmailMessage,
    gemini: Optional[Union[GeminiSummarizer, GroqSummarizer]],
    local: LocalHeuristicSummarizer,
    no_ai: bool,
) -> SummaryResult:
    if no_ai:
        return SummaryResult(
            summary=message.snippet or "No summary available.",
            action_items=["AI disabled."],
            concern="No concern detected.",
            classification="unknown",
            legitimacy_reason="AI disabled.",
            why_received="AI disabled.",
            unsubscribe_instructions="Not available.",
            topic="General",
            provider="none",
            what_it_is="AI disabled.",
            main_offer="AI disabled.",
            key_benefits=["AI disabled."],
            what_it_contains=["AI disabled."],
            how_to_open="Not applicable.",
            important_notes=[],
            what_you_should_do=["Enable AI for insights."],
        )

    if gemini:
        try:
            return gemini.summarize(message)
        except Exception as exc:  # noqa: BLE001 - surface fallback without failing
            print(f"Gemini failed, using local summarizer: {exc}", file=sys.stderr)

    return local.summarize(message)


def _export_record(message: EmailMessage, summary: SummaryResult) -> dict:
    return {
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
        "labels": message.labels,
        "is_unread": message.is_unread,
        "list_unsubscribe": message.list_unsubscribe,
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


def _export_filename() -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"mail_summary_{stamp}.json"


def _render_table(records: List[dict]) -> None:
    table = Table(title="Gmail Summaries")
    table.add_column("Status", width=8)
    table.add_column("From", style="cyan", width=28)
    table.add_column("Subject", style="magenta", width=40)
    table.add_column("Date", width=20)
    table.add_column("Summary", width=60)
    table.add_column("Concern", width=20)

    for record in records:
        status = "Unread" if record["is_unread"] else "Read"
        table.add_row(
            status,
            _truncate(record["from"], 28),
            _truncate(record["subject"], 40),
            _truncate(record["date"], 20),
            _truncate(record["summary"], 60),
            _truncate(record["concern"], 20),
        )

    console = Console()
    console.print(table)


def _truncate(text: str, max_len: int) -> str:
    text = text or ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
