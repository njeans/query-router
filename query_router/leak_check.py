"""
Leak checker: validates that a candidate fragment leaks no sensitive info.

SafeFragment can ONLY be constructed via check_fragment() in this module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple

from query_router.sanitize import PlaceholderMap, SanitizedQuery

# ---------------------------------------------------------------------------
# SafeFragment — only constructible here via _create_safe_fragment
# ---------------------------------------------------------------------------

# Module-private sentinel so no other module can forge a SafeFragment
_SAFE_TOKEN = object()


@dataclass(frozen=True)
class SafeFragment:
    """An immutable fragment that has passed all leak checks.

    Cannot be constructed outside this module — the _token parameter
    is a private sentinel object.
    """
    text: str
    _token: object

    def __post_init__(self):
        if self._token is not _SAFE_TOKEN:
            raise TypeError(
                "SafeFragment cannot be constructed directly. "
                "Use leak_check.check_fragment()."
            )

    def __str__(self) -> str:
        return self.text


def _create_safe_fragment(text: str) -> SafeFragment:
    return SafeFragment(text=text, _token=_SAFE_TOKEN)


# ---------------------------------------------------------------------------
# Rejection
# ---------------------------------------------------------------------------

@dataclass
class LeakCheckResult:
    passed: bool
    fragment: SafeFragment | None
    reason: str | None = None


# ---------------------------------------------------------------------------
# Deterministic checks
# ---------------------------------------------------------------------------

_PLACEHOLDER_RE = re.compile(r"\[[A-Z_]+_\d+\]")

# Generic PII regexes (subset used as backstop)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_URL_RE = re.compile(r"https?://[^\s,)\"']+")
_HOSTNAME_RE = re.compile(
    r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)"
    r"{1,}(?:com|org|net|io|dev|edu|gov|co|us|uk|app|xyz)\b"
)
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_PHONE_RE = re.compile(
    r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
)


# Common English words that should never trigger a partial-token match
_STOPWORDS = frozenset({
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "had",
    "her", "was", "one", "our", "out", "day", "get", "has", "him", "his",
    "how", "its", "may", "new", "now", "old", "see", "way", "who", "did",
    "got", "let", "say", "she", "too", "use", "type", "code", "will",
    "with", "have", "from", "this", "that", "they", "been", "said",
    "each", "make", "like", "long", "look", "many", "some", "than",
    "them", "then", "what", "when", "your", "about", "could", "after",
    "other", "which", "their", "there", "would", "first", "these",
})


def _extract_partial_tokens(placeholder_map: PlaceholderMap) -> List[str]:
    """Build a list of partial tokens from placeholder values.

    E.g. for 'Acme Robotics' also produce 'Acme' and 'Robotics'.
    For 'api.example.com' also produce 'api.example' and 'example.com' and 'example'.
    Common English stopwords are excluded to avoid false positives.
    """
    partials: List[str] = []
    for value in placeholder_map.values:
        val_lower = value.lower()
        # Always add the full value
        if val_lower not in _STOPWORDS:
            partials.append(val_lower)
        # Split on whitespace for multi-word entities
        words = value.split()
        if len(words) > 1:
            for w in words:
                wl = w.lower()
                if len(wl) >= 4 and wl not in _STOPWORDS:
                    partials.append(wl)
        # Split hostnames on dots
        if "." in value:
            parts = value.split(".")
            for p in parts:
                pl = p.lower()
                if len(pl) >= 4 and pl not in _STOPWORDS:
                    partials.append(pl)
            # Also sub-domains: 'api.example.com' → 'api.example', 'example.com'
            for i in range(len(parts)):
                sub = ".".join(parts[i:])
                if len(sub) >= 4:
                    partials.append(sub.lower())
                sub2 = ".".join(parts[: i + 1])
                if len(sub2) >= 4:
                    partials.append(sub2.lower())
    return list(set(partials))


def _extract_numbers_from_query(original_query: str) -> List[str]:
    """Pull out all numbers from the original query."""
    return re.findall(r"\d+", original_query)


def check_fragment_deterministic(
    fragment_text: str,
    sanitized_query: SanitizedQuery,
) -> Tuple[bool, str | None]:
    """Run all deterministic (non-LLM) leak checks.

    Returns (passed, reason_if_failed).
    """
    text_lower = fragment_text.lower()

    # 1. No placeholder map value (case-insensitive, including partial tokens)
    partials = _extract_partial_tokens(sanitized_query.placeholder_map)
    for partial in partials:
        # Use word-boundary match to avoid false positives on common substrings
        if re.search(r'\b' + re.escape(partial) + r'\b', text_lower):
            return False, f"Fragment contains placeholder value token: '{partial}'"

    # 2. No placeholder patterns like [PERSON_1]
    if _PLACEHOLDER_RE.search(fragment_text):
        return False, "Fragment contains placeholder pattern"

    # 3. No number, date, URL, email, hostname from original query
    original_numbers = _extract_numbers_from_query(sanitized_query.original_query)
    fragment_numbers = re.findall(r"\d+", fragment_text)
    for num in fragment_numbers:
        if num in original_numbers and len(num) >= 2:
            return False, f"Fragment contains number from original query: '{num}'"

    # Check URLs/emails/hostnames from original
    for pattern in [_URL_RE, _EMAIL_RE, _HOSTNAME_RE, _IP_RE]:
        original_matches = set(m.group().lower() for m in pattern.finditer(sanitized_query.original_query))
        fragment_matches = set(m.group().lower() for m in pattern.finditer(fragment_text))
        overlap = original_matches & fragment_matches
        if overlap:
            return False, f"Fragment contains identifiable pattern from original: {overlap}"

    # 4. PII backstop — no emails, URLs, hostnames, IPs, phones in fragment at all
    for label, pat in [
        ("email", _EMAIL_RE),
        ("URL", _URL_RE),
        ("hostname", _HOSTNAME_RE),
        ("IP address", _IP_RE),
        ("phone number", _PHONE_RE),
    ]:
        if pat.search(fragment_text):
            return False, f"Fragment contains {label}"

    return True, None


# ---------------------------------------------------------------------------
# Full check (deterministic + LLM judge)
# ---------------------------------------------------------------------------

async def check_fragment(
    fragment_text: str,
    sanitized_query: SanitizedQuery,
    llm_judge=None,
) -> LeakCheckResult:
    """Full leak check: deterministic rules, then optional LLM judge.

    llm_judge: an async callable(fragment_text) -> bool (True = identifying).
    """
    passed, reason = check_fragment_deterministic(fragment_text, sanitized_query)
    if not passed:
        return LeakCheckResult(passed=False, fragment=None, reason=reason)

    # LLM judge: "Could this question identify a specific person, org, or situation?"
    if llm_judge is not None:
        is_identifying = await llm_judge(fragment_text)
        if is_identifying:
            return LeakCheckResult(
                passed=False,
                fragment=None,
                reason="LLM judge: fragment could identify a specific person/org/situation",
            )

    return LeakCheckResult(
        passed=True,
        fragment=_create_safe_fragment(fragment_text),
    )


async def cross_fragment_check(
    fragments: List[SafeFragment],
    sanitized_query: SanitizedQuery,
    llm_cross_judge=None,
) -> Tuple[bool, str | None]:
    """Cross-fragment check: can an LLM reconstruct identifying details
    from all fragments together?

    llm_cross_judge: async callable(fragments_text) -> list[str] of guessed entities.
    Returns (passed, reason).
    """
    if llm_cross_judge is None:
        return True, None

    fragment_texts = [f.text for f in fragments]
    guesses = await llm_cross_judge(fragment_texts)

    # Compare guesses against placeholder map values
    real_values = [v.lower() for v in sanitized_query.placeholder_map.values]
    for guess in guesses:
        guess_lower = guess.lower().strip()
        for real in real_values:
            if guess_lower == real or (len(guess_lower) >= 3 and guess_lower in real):
                return False, f"Cross-fragment: adversary reconstructed '{guess}'"

    return True, None
