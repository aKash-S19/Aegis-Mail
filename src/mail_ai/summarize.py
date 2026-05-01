from __future__ import annotations

import html as html_lib
import json
import re
import time
from typing import List

import requests

from .models import EmailMessage, SummaryResult


class GeminiSummarizer:
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model
        self._resolved_model: str | None = None
        self._model_cache: list[str] | None = None

    def _list_models(self) -> list[str]:
        if self._model_cache is not None:
            return self._model_cache
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models?key="
            f"{self.api_key}"
        )
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        data = response.json()
        models = []
        for item in data.get("models", []):
            name = item.get("name", "")
            if name.startswith("models/"):
                name = name.split("/", 1)[1]
            if name:
                models.append(name)
        self._model_cache = models
        return models

    def _resolve_model(self) -> str:
        if self._resolved_model:
            return self._resolved_model
        try:
            models = self._list_models()
        except Exception:
            self._resolved_model = self.model
            return self._resolved_model

        if not models:
            self._resolved_model = self.model
            return self._resolved_model

        if self.model in models:
            self._resolved_model = self.model
            return self._resolved_model

        fallbacks = [
            "gemini-1.5-flash",
            "gemini-1.5-flash-latest",
            "gemini-1.5-flash-001",
            "gemini-1.5-flash-002",
            "gemini-1.5-pro",
            "gemini-1.5-pro-latest",
            "gemini-1.5-pro-001",
            "gemini-1.0-pro",
            "gemini-pro",
        ]
        for candidate in fallbacks:
            if candidate in models:
                self._resolved_model = candidate
                return self._resolved_model

        self._resolved_model = models[0]
        return self._resolved_model

    def _candidate_models(self) -> list[str]:
        try:
            models = self._list_models()
        except Exception:
            return [self.model]
        if not models:
            return [self.model]
        preferred = [
            "gemini-1.5-flash",
            "gemini-1.5-flash-latest",
            "gemini-1.5-flash-001",
            "gemini-1.5-flash-002",
            "gemini-1.5-pro",
            "gemini-1.5-pro-latest",
            "gemini-1.5-pro-001",
            "gemini-1.0-pro",
            "gemini-pro",
        ]
        ordered = [name for name in preferred if name in models]
        for name in models:
            if name not in ordered:
                ordered.append(name)
        return ordered

    def _request(self, prompt: str, model: str) -> requests.Response:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={self.api_key}"
        )
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 768,
            },
        }
        retry_delays = [0.4, 0.8]
        response = requests.post(url, json=payload, timeout=30)
        for delay in retry_delays:
            if response.status_code not in {429, 503}:
                return response
            time.sleep(delay)
            response = requests.post(url, json=payload, timeout=30)
        return response

    def summarize(self, email: EmailMessage) -> SummaryResult:
        prompt = _build_prompt(email)
        model = self._resolve_model() if self.model == "auto" else self.model
        response = self._request(prompt, model)
        if response.status_code in {404, 429, 503}:
            for candidate in self._candidate_models():
                if candidate == model:
                    continue
                response = self._request(prompt, candidate)
                if response.status_code < 400:
                    break
        response.raise_for_status()
        data = response.json()
        text = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        return _parse_summary(text, provider="gemini")


class GroqSummarizer:
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def _request(self, prompt: str) -> requests.Response:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        retry_delays = [0.4, 0.8]
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        for delay in retry_delays:
            if response.status_code not in {429, 503}:
                return response
            time.sleep(delay)
            response = requests.post(url, headers=headers, json=payload, timeout=30)
        return response

    def summarize(self, email: EmailMessage) -> SummaryResult:
        prompt = _build_prompt(email)
        response = self._request(prompt)
        response.raise_for_status()
        data = response.json()
        text = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        return _parse_summary(text, provider="groq")


def _build_prompt(email: EmailMessage) -> str:
    body = _clean_ai_text(email.body or email.snippet)
    return (
        "You are an assistant that summarizes emails for a user. "
        "Return ONLY JSON (no Markdown, no code fences) with keys: summary, action_items, concern, classification, "
        "legitimacy_reason, why_received, unsubscribe_instructions, topic, "
        "what_it_is, main_offer, key_benefits, what_it_contains, how_to_open, "
        "important_notes, what_you_should_do. "
        "summary: 1-3 sentences, no URLs, do not copy the email body. "
        "action_items: list of 0-5 short strings. "
        "concern: short phrase about urgency or risk. "
        "classification: one of legit, spam, scam, unknown. "
        "legitimacy_reason: short reason for the classification. "
        "why_received: short reason why the user got this email. "
        "unsubscribe_instructions: short steps or 'Not available'. "
        "topic: 2-5 words describing the mail topic (e.g., security alert, billing). "
        "what_it_is: 1 sentence plain English. "
        "main_offer: 1 sentence describing the main offer or core purpose. "
        "key_benefits: list of 2-5 short bullets. "
        "what_it_contains: list of 1-4 short bullets. "
        "how_to_open: 1-3 short steps or 'Not applicable'. "
        "important_notes: list of 0-3 short bullets. "
        "what_you_should_do: list of 1-3 short bullets.\n"
        "Return valid JSON only. Example: {\"summary\":\"...\",\"action_items\":[\"...\"],\"concern\":\"...\",\"classification\":\"legit\",\"legitimacy_reason\":\"...\",\"why_received\":\"...\",\"unsubscribe_instructions\":\"...\",\"topic\":\"...\",\"what_it_is\":\"...\",\"main_offer\":\"...\",\"key_benefits\":[\"...\"],\"what_it_contains\":[\"...\"],\"how_to_open\":\"...\",\"important_notes\":[\"...\"],\"what_you_should_do\":[\"...\"]}\n\n"
        f"From: {email.sender}\n"
        f"From Email: {email.sender_email}\n"
        f"To: {email.to}\n"
        f"To Emails: {', '.join(email.to_emails)}\n"
        f"Date: {email.date}\n"
        f"Subject: {email.subject}\n"
        f"Snippet: {email.snippet}\n"
        f"List-Unsubscribe: {', '.join(email.list_unsubscribe)}\n"
        f"Attachments: {', '.join([a.filename for a in email.attachments])}\n"
        f"Authentication-Results: {email.auth_results}\n\n"
        f"Body (trimmed):\n{body}\n"
    )


def _parse_summary(text: str, provider: str) -> SummaryResult:
    extracted = _extract_json(text)
    if not extracted:
        extracted = _parse_structured_text(text)
    if not extracted:
        extracted = _extract_partial_json_fields(text)
    else:
        partial = _extract_partial_json_fields(text)
        for key, value in partial.items():
            if key not in extracted or not extracted.get(key):
                extracted[key] = value

    fallback_text = "" if text.strip().startswith("{") else text.strip()
    summary = extracted.get("summary") or fallback_text or "No summary available."
    summary = _sanitize_summary(summary)
    action_items = [
        _clean_ai_text(item) for item in _ensure_list(extracted.get("action_items"))
    ]
    action_items = [item for item in action_items if item]
    concern = extracted.get("concern") or "No concern detected."
    classification = _normalize_classification(extracted.get("classification"))
    legitimacy_reason = extracted.get("legitimacy_reason") or "No assessment."
    why_received = extracted.get("why_received") or "Not specified."
    unsubscribe_instructions = (
        extracted.get("unsubscribe_instructions") or "Not available."
    )
    topic = extracted.get("topic") or "General"
    what_it_is = _clean_ai_text(extracted.get("what_it_is") or "")
    main_offer = _clean_ai_text(extracted.get("main_offer") or "")
    key_benefits = [
        _clean_ai_text(item) for item in _ensure_list(extracted.get("key_benefits"))
    ]
    what_it_contains = [
        _clean_ai_text(item)
        for item in _ensure_list(extracted.get("what_it_contains"))
    ]
    how_to_open = _clean_ai_text(extracted.get("how_to_open") or "")
    important_notes = [
        _clean_ai_text(item)
        for item in _ensure_list(extracted.get("important_notes"))
    ]
    what_you_should_do = [
        _clean_ai_text(item)
        for item in _ensure_list(extracted.get("what_you_should_do"))
    ]

    what_it_is = what_it_is or summary or "Email update."
    key_benefits = [item for item in key_benefits if item]
    what_it_contains = [item for item in what_it_contains if item]
    if not main_offer and what_it_contains:
        main_offer = what_it_contains[0]
    main_offer = main_offer or "Not specified."
    if not key_benefits and len(what_it_contains) > 1:
        key_benefits = what_it_contains[1:]
    important_notes = [item for item in important_notes if item]
    what_you_should_do = [item for item in what_you_should_do if item]
    how_to_open = how_to_open or "Not applicable."

    if isinstance(action_items, str):
        action_items = [action_items]
    if not isinstance(action_items, list):
        action_items = []

    return SummaryResult(
        summary=summary.strip(),
        action_items=[str(item).strip() for item in action_items if str(item).strip()],
        concern=concern.strip(),
        classification=classification,
        legitimacy_reason=str(legitimacy_reason).strip(),
        why_received=str(why_received).strip(),
        unsubscribe_instructions=str(unsubscribe_instructions).strip(),
        topic=str(topic).strip(),
        provider=provider,
        what_it_is=str(what_it_is).strip(),
        main_offer=str(main_offer).strip(),
        key_benefits=[
            str(item).strip() for item in key_benefits if str(item).strip()
        ],
        what_it_contains=[
            str(item).strip()
            for item in what_it_contains
            if str(item).strip()
        ],
        how_to_open=str(how_to_open).strip(),
        important_notes=[
            str(item).strip()
            for item in important_notes
            if str(item).strip()
        ],
        what_you_should_do=[
            str(item).strip()
            for item in what_you_should_do
            if str(item).strip()
        ],
    )


def _ensure_list(value: object) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [value]
    return [str(value)]


def _normalize_classification(value: object) -> str:
    normalized = str(value or "unknown").strip().lower()
    allowed = {"legit", "spam", "scam", "unknown"}
    return normalized if normalized in allowed else "unknown"


def _sanitize_summary(text: str) -> str:
    text = _clean_ai_text(text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= 480:
        return text
    return _shorten_text(text, 480)


def _shorten_text(text: str, limit: int) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    output = ""
    for sentence in sentences:
        if not sentence:
            continue
        candidate = f"{output} {sentence}".strip()
        if len(candidate) > limit:
            break
        output = candidate
    if output:
        return output
    return text[: limit - 3].rstrip() + "..."


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    match = re.match(
        r"^```(?:json)?\s*(.*?)\s*```$", stripped, flags=re.DOTALL | re.IGNORECASE
    )
    if match:
        return match.group(1).strip()
    stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.IGNORECASE).strip()
    stripped = re.sub(r"```$", "", stripped).strip()
    return stripped


def _extract_json(text: str) -> dict:
    text = _strip_code_fences(text)
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def _extract_partial_json_fields(text: str) -> dict:
    if not text:
        return {}

    result: dict[str, object] = {}
    scalar_keys = [
        "summary",
        "what_it_is",
        "main_offer",
        "how_to_open",
        "topic",
        "concern",
        "why_received",
        "unsubscribe_instructions",
        "legitimacy_reason",
        "classification",
    ]
    list_keys = [
        "action_items",
        "key_benefits",
        "what_it_contains",
        "important_notes",
        "what_you_should_do",
    ]

    for key in scalar_keys:
        match = re.search(rf'"{key}"\s*:\s*"([^"]*)"', text, flags=re.DOTALL)
        if match:
            result[key] = match.group(1).strip()

    for key in list_keys:
        match = re.search(rf'"{key}"\s*:\s*\[(.*?)\]', text, flags=re.DOTALL)
        if match:
            items = re.findall(r'"([^"]+)"', match.group(1))
            cleaned = [item.strip() for item in items if item.strip()]
            if cleaned:
                result[key] = cleaned

    return result


def _parse_structured_text(text: str) -> dict:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return {}

    label_map = {
        "what it is": "what_it_is",
        "main offer": "main_offer",
        "key benefits": "key_benefits",
        "what it contains": "what_it_contains",
        "how to open": "how_to_open",
        "important notes": "important_notes",
        "what you should do": "what_you_should_do",
        "topic": "topic",
        "concern": "concern",
        "why received": "why_received",
    }
    list_keys = {
        "key_benefits",
        "what_it_contains",
        "important_notes",
        "what_you_should_do",
    }

    data: dict[str, object] = {}
    current_key: str | None = None

    for raw_line in lines:
        line = raw_line.strip()
        lower = line.lower()
        matched_label = None
        for label, key in label_map.items():
            if lower.startswith(label):
                matched_label = key
                break

        if matched_label:
            current_key = matched_label
            if ":" in line:
                value = line.split(":", 1)[1].strip()
                if value:
                    data[current_key] = value
            else:
                if current_key in list_keys:
                    data.setdefault(current_key, [])
            continue

        if not current_key:
            continue

        if current_key in list_keys:
            item = re.sub(r"^[-*\u2022\d+.)\s]+", "", line).strip()
            if item:
                data.setdefault(current_key, []).append(item)
        else:
            previous = str(data.get(current_key, "")).strip()
            data[current_key] = f"{previous} {line}".strip() if previous else line

    return data


def _clean_ai_text(text: object) -> str:
    value = html_lib.unescape(str(text or ""))
    if not value:
        return ""
    value = re.sub(
        r"<\s*(script|style)[^>]*>.*?<\s*/\1\s*>",
        "",
        value,
        flags=re.IGNORECASE | re.DOTALL,
    )
    value = re.sub(r"<\s*br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"</p\s*>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


class LocalHeuristicSummarizer:
    def summarize(self, email: EmailMessage) -> SummaryResult:
        content = _clean_ai_text(email.body or email.snippet)
        sentences = _split_sentences(content)
        summary = _sanitize_summary(_summarize_sentences(sentences))
        action_items = _extract_actions(sentences)
        concern = _detect_concern(content)
        classification = _classify_message(content, email.list_unsubscribe)
        legitimacy_reason = _legitimacy_reason(classification, content)
        why_received = _why_received_reason(content, email.list_unsubscribe)
        unsubscribe_instructions = _unsubscribe_hint(email.list_unsubscribe)
        topic = _detect_topic(content)
        what_it_is = _what_it_is_hint(email, topic)
        what_it_contains = _what_it_contains_hint(content)
        how_to_open = _how_to_open_hint(content, email)
        important_notes = _important_notes_hint(content)
        what_you_should_do = _what_you_should_do_hint(action_items, email)
        main_offer = _main_offer_hint(content)
        key_benefits = _key_benefits_hint(content)
        return SummaryResult(
            summary=summary,
            action_items=action_items,
            concern=concern,
            classification=classification,
            legitimacy_reason=legitimacy_reason,
            why_received=why_received,
            unsubscribe_instructions=unsubscribe_instructions,
            topic=topic,
            provider="local_heuristic",
            what_it_is=what_it_is,
            main_offer=main_offer,
            key_benefits=key_benefits,
            what_it_contains=what_it_contains,
            how_to_open=how_to_open,
            important_notes=important_notes,
            what_you_should_do=what_you_should_do,
        )


def _split_sentences(text: str) -> List[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [part.strip() for part in parts if part.strip()]


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z]{3,}", text.lower())


def _summarize_sentences(sentences: List[str]) -> str:
    if not sentences:
        return "No summary available."

    stopwords = {
        "the",
        "and",
        "for",
        "you",
        "your",
        "with",
        "that",
        "this",
        "from",
        "are",
        "was",
        "have",
        "has",
        "will",
        "not",
        "but",
        "they",
        "their",
        "our",
        "its",
        "can",
        "may",
        "please",
        "thanks",
    }

    scores = []
    word_freq: dict[str, int] = {}
    for sentence in sentences:
        for word in _tokenize(sentence):
            if word in stopwords:
                continue
            word_freq[word] = word_freq.get(word, 0) + 1

    for sentence in sentences:
        score = 0
        for word in _tokenize(sentence):
            if word in stopwords:
                continue
            score += word_freq.get(word, 0)
        scores.append(score)

    ranked = sorted(zip(scores, sentences), reverse=True)
    top_sentences = [sent for _, sent in ranked[: min(2, len(ranked))]]
    return " ".join(top_sentences).strip()


def _extract_actions(sentences: List[str]) -> List[str]:
    action_keywords = [
        "action required",
        "verify",
        "confirm",
        "update",
        "submit",
        "pay",
        "payment",
        "respond",
        "reply",
        "review",
        "complete",
        "approve",
        "sign",
        "activate",
        "reset",
    ]
    actions: List[str] = []
    for sentence in sentences:
        lower = sentence.lower()
        if any(keyword in lower for keyword in action_keywords):
            actions.append(sentence)
        if len(actions) >= 3:
            break
    return actions or ["No action indicated."]


def _detect_concern(text: str) -> str:
    concern_keywords = [
        "urgent",
        "overdue",
        "failed",
        "security",
        "alert",
        "fraud",
        "suspicious",
        "blocked",
        "deactivated",
        "payment",
        "penalty",
        "refund",
    ]
    lower = (text or "").lower()
    if any(keyword in lower for keyword in concern_keywords):
        return "Needs attention."
    return "No immediate concern detected."


def _classify_message(text: str, list_unsubscribe: List[str]) -> str:
    lower = (text or "").lower()
    scam_keywords = [
        "verify your account",
        "password expired",
        "urgent",
        "gift card",
        "wire transfer",
        "crypto",
        "wallet",
        "limited time",
    ]
    spam_keywords = [
        "win",
        "free",
        "bonus",
        "promotion",
        "sale",
        "deal",
        "offer",
    ]
    if any(keyword in lower for keyword in scam_keywords):
        return "scam"
    if any(keyword in lower for keyword in spam_keywords):
        return "spam"
    if list_unsubscribe:
        return "legit"
    return "unknown"


def _legitimacy_reason(classification: str, text: str) -> str:
    if classification == "scam":
        return "Contains urgency or sensitive account language."
    if classification == "spam":
        return "Looks like a marketing or promotional email."
    if classification == "legit":
        return "Sender provides a clear unsubscribe option."
    if text:
        return "Not enough signals to determine legitimacy."
    return "No content to assess."


def _why_received_reason(text: str, list_unsubscribe: List[str]) -> str:
    if list_unsubscribe:
        return "Likely subscribed or opted in to updates from the sender."
    if "invoice" in (text or "").lower():
        return "Likely related to a transaction or billing notice."
    return "Not enough context to determine why it was sent."


def _unsubscribe_hint(list_unsubscribe: List[str]) -> str:
    if not list_unsubscribe:
        return "Not available."
    return "Use the sender's unsubscribe link or email listed."


def _detect_topic(text: str) -> str:
    lower = (text or "").lower()
    topics = {
        "Security alert": ["login", "password", "security", "suspicious"],
        "Billing": ["invoice", "payment", "receipt", "refund", "tax", "gst"],
        "Jobs": ["job", "interview", "resume", "application"],
        "Shipping": ["shipment", "delivery", "tracking", "order"],
        "Marketing": ["discount", "offer", "promo", "sale", "newsletter"],
        "Account update": ["account", "subscription", "plan", "upgrade", "trial"],
    }
    for topic, keywords in topics.items():
        if any(keyword in lower for keyword in keywords):
            return topic
    return "General"


def _what_it_is_hint(email: EmailMessage, topic: str) -> str:
    sender = email.sender_name or email.sender_email or email.sender or "the sender"
    if topic and topic != "General":
        return f"An email about {topic.lower()} from {sender}."
    return f"An email update from {sender}."


def _what_it_contains_hint(content: str) -> List[str]:
    sentences = _split_sentences(content)
    if not sentences:
        return ["No details available in the email body."]
    return sentences[:2]


def _how_to_open_hint(content: str, email: EmailMessage) -> str:
    lower = (content or "").lower()
    has_attachment = bool(getattr(email, "attachments", []))
    if "password" in lower and "pan" in lower:
        return "Open the attachment and use your PAN in capital letters as the password."
    if "password" in lower and has_attachment:
        return "Open the attachment and use the password mentioned in the email."
    if has_attachment:
        return "Open the attached file to view the details."
    return "Not applicable."


def _important_notes_hint(content: str) -> List[str]:
    lower = (content or "").lower()
    notes: List[str] = []
    if "not investment advice" in lower or "not advice" in lower:
        notes.append("It is informational and not investment advice.")
    if "market risks" in lower or "market risk" in lower:
        notes.append("Standard warning: markets involve risk.")
    if "disclaimer" in lower:
        notes.append("Contains a legal disclaimer from the sender.")
    return notes


def _what_you_should_do_hint(action_items: List[str], email: EmailMessage) -> List[str]:
    suggestions: List[str] = []
    skip_phrases = ["registered office", "disclaimer", "privacy policy", "terms"]
    for item in action_items:
        cleaned = str(item or "").strip()
        if not cleaned or cleaned == "No action indicated.":
            continue
        if any(phrase in cleaned.lower() for phrase in skip_phrases):
            continue
        suggestions.append(cleaned)
    if not suggestions and getattr(email, "attachments", []):
        suggestions.append("Open the attachment and review the details.")
    if not suggestions:
        suggestions.append("No urgent action unless something looks incorrect.")
    return suggestions[:3]


def _extract_bullets(text: str) -> List[str]:
    if not text:
        return []
    raw = text.replace("\u2022", "\n\u2022")
    raw = re.sub(r"\s*-\s+", "\n- ", raw)
    parts = re.split(r"\n\s*(?:\u2022|-|\d+\.)\s+", raw)
    bullets = [part.strip(" .") for part in parts if part.strip()]
    return [bullet for bullet in bullets if len(bullet.split()) >= 3]


def _main_offer_hint(content: str) -> str:
    lower = (content or "").lower()
    match = re.search(r"(\d{1,3})-day\s+trial", lower)
    if match:
        return f"A {match.group(1)}-day free trial for the service mentioned."
    if "free trial" in lower or "trial" in lower:
        return "A free trial for the service mentioned in the email."
    if "support plan" in lower:
        return "A new support plan or upgrade from the sender."
    if "offer" in lower or "limited time" in lower:
        return "A limited-time offer from the sender."
    if "update" in lower:
        return "An informational update from the sender."
    return "Not specified."


def _key_benefits_hint(content: str) -> List[str]:
    lower = (content or "").lower()
    benefits: List[str] = []
    bullets = _extract_bullets(content)
    for bullet in bullets:
        if len(benefits) >= 5:
            break
        benefits.append(bullet)
    if benefits:
        return benefits
    if "24/7" in lower or "24x7" in lower or "24-7" in lower:
        benefits.append("24/7 access to support.")
    if "response" in lower and "minute" in lower:
        benefits.append("Faster response time for critical issues.")
    if "ai" in lower or "artificial intelligence" in lower:
        benefits.append("AI assistance to speed up diagnosis.")
    if "monitor" in lower or "insight" in lower:
        benefits.append("Proactive monitoring and actionable insights.")
    if "cost" in lower and "performance" in lower:
        benefits.append("Performance and cost optimization guidance.")
    return benefits
