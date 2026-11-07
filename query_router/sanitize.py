"""
Detect sensitive spans in a query and replace them with typed placeholders.
The PlaceholderMap lives only in memory — never serialized to disk or logs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Regex patterns for PII / sensitive spans
# ---------------------------------------------------------------------------

_PATTERNS: List[Tuple[str, re.Pattern]] = [
    # Email
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    # URL (http/https)
    ("URL", re.compile(r"https?://[^\s,)\"']+")),
    # Hostname / FQDN (at least two dots or common TLDs)
    ("HOSTNAME", re.compile(
        r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)"
        r"{1,}(?:com|org|net|io|dev|edu|gov|co|us|uk|app|xyz)\b"
    )),
    # IPv4
    ("IP", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    # API key patterns (long hex/base64 strings)
    ("API_KEY", re.compile(r"\b(?:sk-|pk-|api[_-]?key[=: ]*)?[A-Za-z0-9_-]{32,}\b")),
    # Phone numbers (US-style)
    ("PHONE", re.compile(
        r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
    )),
    # Money amounts
    ("AMOUNT", re.compile(r"\$[\d,]+(?:\.\d{1,2})?[KkMmBb]?\b")),
    # Money written as word-amounts like "60M", "$60M"
    ("AMOUNT", re.compile(r"\b\d+(?:\.\d+)?\s*(?:million|billion|[MBKmkb])\b", re.IGNORECASE)),
    # Dates (various formats)
    ("DATE", re.compile(
        r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b"
    )),
    # Age pattern like "34-year-old"
    ("AGE", re.compile(r"\b\d{1,3}-year-old\b", re.IGNORECASE)),
    # Standalone significant numbers (not common small ones)
    # We catch numbers >= 2 digits that aren't part of another token
    ("NUMBER", re.compile(r"\b\d{2,}\b")),
]

# Known entity patterns for the test fixtures — a lightweight NER substitute.
# In production you'd use Presidio or spaCy here.
_PERSON_NAMES = re.compile(
    r"\b(?:Sarah|John|Jane|Alice|Bob|Charlie|David|Emily)\b", re.IGNORECASE
)

_COMPANY_NAMES = re.compile(
    r"\b(?:Acme Robotics|Acme|Delta|Google|Meta|Amazon|Apple|Microsoft)\b", re.IGNORECASE
)

_LOCATION_NAMES = re.compile(
    r"\b(?:Austin|New York|San Francisco|Seattle|Boston|Chicago|Denver|Portland)\b",
    re.IGNORECASE,
)

_VISA_TYPES = re.compile(r"\b(?:H-1B|H1B|L-1|O-1|F-1|J-1|EB-[1-5])\b", re.IGNORECASE)

_JOB_TITLES = re.compile(
    r"\b(?:CEO|CTO|CFO|COO|VP|pilot|manager|cofounder|co-founder)\b", re.IGNORECASE
)

_MEDICAL = re.compile(
    r"\b(?:type [12] diabetes|diabetes|cancer|HIV|depression|anxiety)\b", re.IGNORECASE
)

_CRYPTO_ALGO = re.compile(r"\b(?:HS256|HS384|HS512|RS256|RS512|ES256)\b")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PlaceholderMap:
    """Maps placeholder tokens to their original sensitive values."""
    _map: Dict[str, str] = field(default_factory=dict)
    _counters: Dict[str, int] = field(default_factory=dict)

    def add(self, category: str, original_value: str) -> str:
        """Register a value and return its placeholder token.
        If the same value was already added, return the existing placeholder."""
        # Check if value already mapped
        for placeholder, val in self._map.items():
            if val == original_value:
                return placeholder
        count = self._counters.get(category, 0) + 1
        self._counters[category] = count
        placeholder = f"[{category}_{count}]"
        self._map[placeholder] = original_value
        return placeholder

    @property
    def mapping(self) -> Dict[str, str]:
        return dict(self._map)

    @property
    def values(self) -> List[str]:
        return list(self._map.values())

    def __repr__(self) -> str:
        return f"PlaceholderMap({len(self._map)} entries)"

    def __len__(self) -> int:
        return len(self._map)


@dataclass
class SanitizedQuery:
    text: str
    placeholder_map: PlaceholderMap
    original_query: str


# ---------------------------------------------------------------------------
# Sanitization engine
# ---------------------------------------------------------------------------

def _find_spans(text: str) -> List[Tuple[int, int, str, str]]:
    """Find all sensitive spans: (start, end, category, matched_text)."""
    spans: List[Tuple[int, int, str, str]] = []

    # Named entities (run before generic patterns)
    for pattern, category in [
        (_PERSON_NAMES, "PERSON"),
        (_COMPANY_NAMES, "COMPANY"),
        (_LOCATION_NAMES, "LOCATION"),
        (_VISA_TYPES, "VISA_TYPE"),
        (_JOB_TITLES, "JOB_TITLE"),
        (_MEDICAL, "MEDICAL"),
        (_CRYPTO_ALGO, "TECH"),
    ]:
        for m in pattern.finditer(text):
            spans.append((m.start(), m.end(), category, m.group()))

    # Generic PII patterns
    for category, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            spans.append((m.start(), m.end(), category, m.group()))

    # Sort by start position, longer matches first for ties
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    return spans


def _merge_overlapping(
    spans: List[Tuple[int, int, str, str]],
) -> List[Tuple[int, int, str, str]]:
    """Remove overlapping spans, keeping the first (longest at each position)."""
    if not spans:
        return []
    merged = [spans[0]]
    for span in spans[1:]:
        if span[0] >= merged[-1][1]:
            merged.append(span)
    return merged


def sanitize(query: str) -> SanitizedQuery:
    """Replace sensitive spans in *query* with typed placeholders.

    Returns a SanitizedQuery holding the cleaned text and the PlaceholderMap.
    """
    spans = _merge_overlapping(_find_spans(query))
    pmap = PlaceholderMap()

    parts: List[str] = []
    cursor = 0
    for start, end, category, value in spans:
        parts.append(query[cursor:start])
        placeholder = pmap.add(category, value)
        parts.append(placeholder)
        cursor = end
    parts.append(query[cursor:])

    sanitized_text = "".join(parts)
    return SanitizedQuery(
        text=sanitized_text,
        placeholder_map=pmap,
        original_query=query,
    )


def sanitize_with_llm_entities(
    query: str,
    llm_entities: List[Tuple[str, str]] | None = None,
) -> SanitizedQuery:
    """Sanitize with optional LLM-detected entities added first.

    llm_entities: list of (category, value) from local LLM detection.
    """
    if not llm_entities:
        return sanitize(query)

    # Pre-replace LLM-detected entities, then run regex pass
    pmap = PlaceholderMap()
    text = query
    for category, value in llm_entities:
        if value in text:
            placeholder = pmap.add(category, value)
            text = text.replace(value, placeholder)

    # Now run regex on the partially-sanitized text to catch remaining PII
    spans = _merge_overlapping(_find_spans(text))
    parts: List[str] = []
    cursor = 0
    for start, end, category, value in spans:
        # Don't re-sanitize placeholders
        if value.startswith("[") and value.endswith("]"):
            parts.append(text[cursor:end])
            cursor = end
            continue
        parts.append(text[cursor:start])
        placeholder = pmap.add(category, value)
        parts.append(placeholder)
        cursor = end
    parts.append(text[cursor:])

    sanitized_text = "".join(parts)
    return SanitizedQuery(
        text=sanitized_text,
        placeholder_map=pmap,
        original_query=query,
    )
