"""Tests for the router — fail-closed logic and no-leak-across-fixtures."""

import pytest

from query_router.leak_check import SafeFragment, _create_safe_fragment
from query_router.remote import RemoteAnswer
from query_router.router import route
from query_router.sanitize import sanitize


# ---------------------------------------------------------------------------
# Mock remote sender that records what it receives
# ---------------------------------------------------------------------------

class MockRemoteSender:
    def __init__(self):
        self.calls: list[SafeFragment] = []

    async def __call__(self, fragment: SafeFragment) -> RemoteAnswer:
        self.calls.append(fragment)
        return RemoteAnswer(
            fragment_text=fragment.text,
            answer=f"Mock answer to: {fragment.text}",
        )


# ---------------------------------------------------------------------------
# Fail-closed test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fail_closed_zero_remote_calls(monkeypatch):
    """When decomposition always returns leaky fragments, router must
    fall back locally with zero remote calls."""
    mock_sender = MockRemoteSender()

    # Return fragments that always leak entity names → deterministic rejection
    async def leaky_decompose(sanitized_query, retry_reason=None):
        return [
            "What should Acme do about this?",
            "Can a cofounder take code from Acme Robotics?",
        ]

    monkeypatch.setattr("query_router.router.decompose", leaky_decompose)

    async def mock_fallback(query):
        return "Local fallback answer"

    monkeypatch.setattr("query_router.router.local_fallback", mock_fallback)

    result = await route(
        "My cofounder at Acme Robotics is threatening to leave.",
        use_llm_sanitize=False,
        use_llm_judges=False,
        remote_send_fn=mock_sender,
    )

    assert result.tier == "local_fallback"
    assert len(mock_sender.calls) == 0, "Fail-closed: no remote calls on fallback"


# ---------------------------------------------------------------------------
# Force fail-closed: mock decompose to always return leaky fragments
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_force_fail_closed(monkeypatch):
    """Force decomposition to return fragments that fail leak check.
    Assert zero remote calls and local_fallback tier."""
    mock_sender = MockRemoteSender()

    # Monkeypatch decompose to return fragments containing original entities
    async def bad_decompose(sanitized_query, retry_reason=None):
        return [
            "What should Acme Robotics do about IP theft?",
            "Can a cofounder take source code legally?",
        ]

    monkeypatch.setattr("query_router.router.decompose", bad_decompose)

    # Also mock local_fallback to avoid needing a live LLM
    async def mock_fallback(query):
        return "Local fallback answer"

    monkeypatch.setattr("query_router.router.local_fallback", mock_fallback)

    result = await route(
        "My cofounder at Acme Robotics is threatening to leave with our "
        "source code. We never signed an IP assignment. What can I do?",
        use_llm_sanitize=False,
        use_llm_judges=False,
        remote_send_fn=mock_sender,
    )

    assert result.tier == "local_fallback"
    assert len(mock_sender.calls) == 0, "Fail-closed: zero remote calls"
    assert result.fallback_reason is not None


# ---------------------------------------------------------------------------
# No-leak-across-all-fixtures test (mocked remote)
# ---------------------------------------------------------------------------

FIXTURES = [
    (
        "pilot_diabetes",
        "I'm a 34-year-old pilot at Delta and just got diagnosed with type 1 diabetes. "
        "Will I lose my medical certificate, and should I tell HR before my next check ride?",
    ),
    (
        "cofounder_ip",
        "My cofounder at Acme Robotics is threatening to leave with our source code. "
        "We never signed an IP assignment. What can I do?",
    ),
    (
        "acquisition",
        "We're considering acquiring a 40-person fintech in Austin at around $60M. "
        "How should we structure earnouts to keep their CTO?",
    ),
    (
        "jwt_leak",
        "Our production API at api.example.com uses JWTs signed with HS256 and the "
        "secret is in a public GitHub repo. How bad is this and how do we rotate without downtime?",
    ),
    (
        "harassment_visa",
        "My manager Sarah keeps scheduling 1:1s after hours and commenting on my appearance. "
        "I'm on an H-1B. Can I report this without risking my visa?",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("name,query", FIXTURES, ids=[f[0] for f in FIXTURES])
async def test_no_placeholder_values_sent_remotely(name, query, monkeypatch):
    """Across every fixture: no string sent remotely may contain any PlaceholderMap value
    or any number from the original query."""
    import re

    mock_sender = MockRemoteSender()

    # Mock decompose to return generic questions that should pass
    generic_questions = [
        "What are the general legal considerations in this type of situation?",
        "What steps should someone take to protect their interests?",
    ]

    async def good_decompose(sanitized_query, retry_reason=None):
        return list(generic_questions)

    monkeypatch.setattr("query_router.router.decompose", good_decompose)

    async def mock_fallback(q):
        return "Local fallback answer"

    monkeypatch.setattr("query_router.router.local_fallback", mock_fallback)

    # Mock recombine to avoid needing a live LLM
    async def mock_recombine(sanitized_query, fragment_answers):
        return "Mock recombined answer"

    monkeypatch.setattr("query_router.router.recombine", mock_recombine)

    result = await route(
        query,
        use_llm_sanitize=False,
        use_llm_judges=False,
        remote_send_fn=mock_sender,
    )

    sq = sanitize(query)

    # Check all fragments sent remotely
    for frag in mock_sender.calls:
        frag_lower = frag.text.lower()

        # No placeholder map values
        for val in sq.placeholder_map.values:
            assert val.lower() not in frag_lower, (
                f"[{name}] Fragment contains placeholder value '{val}': {frag.text}"
            )

        # No numbers from original (2+ digits)
        original_numbers = re.findall(r"\d{2,}", query)
        frag_numbers = re.findall(r"\d{2,}", frag.text)
        for num in frag_numbers:
            assert num not in original_numbers, (
                f"[{name}] Fragment contains number from original: '{num}'"
            )
