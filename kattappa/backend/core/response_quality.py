from __future__ import annotations

import re


STOP_WORDS = {
    "a",
    "about",
    "after",
    "again",
    "all",
    "also",
    "am",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "been",
    "but",
    "by",
    "can",
    "could",
    "do",
    "does",
    "doing",
    "for",
    "from",
    "give",
    "has",
    "have",
    "how",
    "i",
    "if",
    "in",
    "is",
    "it",
    "its",
    "just",
    "like",
    "make",
    "me",
    "my",
    "not",
    "of",
    "on",
    "or",
    "please",
    "should",
    "so",
    "that",
    "the",
    "then",
    "this",
    "to",
    "was",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "why",
    "with",
    "you",
    "your",
}

CONTROL_REPLY_PREFIXES = (
    "approval needed",
    "blocked for safety",
    "i remembered:",
    "local model timed out",
    "backend is offline",
    "connection dropped",
    "speech-to-text is unavailable",
    "screen capture unavailable",
)


def content_terms(text: str) -> list[str]:
    terms: list[str] = []
    for raw in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", text.lower()):
        token = _normalize_token(raw)
        if len(token) < 3 or token in STOP_WORDS or token in terms:
            continue
        terms.append(token)
    return terms


def response_relevance_score(user_input: str, response: str) -> float:
    user_terms = content_terms(user_input)
    if not user_terms:
        return 1.0
    response_terms = set(content_terms(response))
    if not response_terms:
        return 0.0
    overlap = [term for term in user_terms if term in response_terms]
    denominator = min(len(user_terms), 6)
    base_score = len(overlap) / max(denominator, 1)
    if _has_shared_phrase(user_input, response):
        base_score += 0.25
    return min(base_score, 1.0)


def response_looks_related(user_input: str, response: str, threshold: float = 0.22) -> bool:
    if not user_input.strip() or not response.strip():
        return True
    lowered = response.strip().lower()
    if lowered.startswith(CONTROL_REPLY_PREFIXES):
        return True
    user_terms = content_terms(user_input)
    if not user_terms:
        return True
    return response_relevance_score(user_input, response) >= threshold


def topic_phrase(user_input: str, limit: int = 72) -> str:
    clean = " ".join(user_input.strip().split())
    if not clean:
        return "your latest message"
    return clean[:limit] + ("..." if len(clean) > limit else "")


def _normalize_token(token: str) -> str:
    token = token.strip("_-")
    
    # Irregular verbs mapping to base form
    irregulars = {
        "told": "tell",
        "said": "say",
        "wrote": "write",
        "spoke": "speak",
        "gave": "give",
        "shown": "show",
        "showed": "show",
        "did": "do",
    }
    if token in irregulars:
        return irregulars[token]

    # Date / temporal terms mapping to "date"
    months = {
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
        "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec"
    }
    relative_temporal = {"today", "tomorrow", "yesterday", "now"}
    if token in months or token in relative_temporal or re.match(r"^2\d{3}$", token):
        return "date"

    # Time terms mapping to "time"
    if token in {"am", "pm"}:
        return "time"

    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    for suffix in ("ingly", "edly", "ing", "edly", "ed", "ly", "s"):
        if token.endswith(suffix) and len(token) > len(suffix) + 3:
            token = token[: -len(suffix)]
            break
    return token


def _has_shared_phrase(user_input: str, response: str) -> bool:
    user_terms = content_terms(user_input)
    if len(user_terms) < 2:
        return False
    response_terms = content_terms(response)
    response_pairs = set(zip(response_terms, response_terms[1:]))
    return any(pair in response_pairs for pair in zip(user_terms, user_terms[1:]))
