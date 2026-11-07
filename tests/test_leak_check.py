"""Tests for the leak check module — deterministic only (no LLM)."""

import pytest

from query_router.leak_check import (
    SafeFragment,
    _create_safe_fragment,
    check_fragment,
    check_fragment_deterministic,
)
from query_router.sanitize import sanitize


# ---------------------------------------------------------------------------
# SafeFragment construction
# ---------------------------------------------------------------------------

def test_safe_fragment_cannot_be_constructed_directly():
    """SafeFragment rejects construction without the private token."""
    with pytest.raises(TypeError, match="cannot be constructed directly"):
        SafeFragment(text="hello", _token=None)


def test_safe_fragment_rejects_wrong_token():
    with pytest.raises(TypeError):
        SafeFragment(text="hello", _token="not_the_token")


def test_safe_fragment_str():
    sf = _create_safe_fragment("test question")
    assert str(sf) == "test question"


# ---------------------------------------------------------------------------
# Deterministic checks — fragments that MUST FAIL
# ---------------------------------------------------------------------------

_ACME_QUERY = (
    "My cofounder at Acme Robotics is threatening to leave with our "
    "source code. We never signed an IP assignment. What can I do?"
)

_ACQUISITION_QUERY = (
    "We're considering acquiring a 40-person fintech in Austin at "
    "around $60M. How should we structure earnouts to keep their CTO?"
)

_JWT_QUERY = (
    "Our production API at api.example.com uses JWTs signed with "
    "HS256 and the secret is in a public GitHub repo. How bad is "
    "this and how do we rotate without downtime?"
)

_HARASSMENT_QUERY = (
    "My manager Sarah keeps scheduling 1:1s after hours and "
    "commenting on my appearance. I'm on an H-1B. Can I report "
    "this without risking my visa?"
)


class TestMustFail:
    """Fragments containing leaked info must be rejected."""

    def test_contains_acme(self):
        sq = sanitize(_ACME_QUERY)
        passed, reason = check_fragment_deterministic(
            "What should Acme do about IP?", sq
        )
        assert not passed
        assert "Acme" in (reason or "").lower() or "placeholder value" in (reason or "").lower()

    def test_contains_austin(self):
        sq = sanitize(_ACQUISITION_QUERY)
        passed, reason = check_fragment_deterministic(
            "How to acquire a company in Austin?", sq
        )
        assert not passed

    def test_contains_60m(self):
        sq = sanitize(_ACQUISITION_QUERY)
        passed, reason = check_fragment_deterministic(
            "How to structure a $60M acquisition?", sq
        )
        assert not passed

    def test_contains_hostname(self):
        sq = sanitize(_JWT_QUERY)
        passed, reason = check_fragment_deterministic(
            "Is api.example.com vulnerable?", sq
        )
        assert not passed

    def test_contains_sarah(self):
        sq = sanitize(_HARASSMENT_QUERY)
        passed, reason = check_fragment_deterministic(
            "My manager Sarah is harassing me", sq
        )
        assert not passed

    def test_contains_placeholder_pattern(self):
        sq = sanitize(_ACME_QUERY)
        passed, reason = check_fragment_deterministic(
            "What should [COMPANY_1] do about IP?", sq
        )
        assert not passed
        assert "placeholder pattern" in (reason or "")

    def test_contains_number_from_original(self):
        sq = sanitize(_ACQUISITION_QUERY)
        passed, reason = check_fragment_deterministic(
            "How to retain employees in a 40-person company?", sq
        )
        assert not passed

    def test_contains_email(self):
        sq = sanitize("Send the report to john@example.com by Friday.")
        passed, reason = check_fragment_deterministic(
            "How to email john@example.com?", sq
        )
        assert not passed

    def test_contains_partial_company_name(self):
        """Even a partial token like just 'Robotics' from 'Acme Robotics' should fail."""
        sq = sanitize(_ACME_QUERY)
        passed, reason = check_fragment_deterministic(
            "How do robotics companies handle IP?", sq
        )
        assert not passed


class TestMustPass:
    """Generic fragments with no leaked info must pass."""

    def test_generic_ip_question(self):
        sq = sanitize(_ACME_QUERY)
        passed, reason = check_fragment_deterministic(
            "What legal protections exist for intellectual property when no formal agreement was signed?",
            sq,
        )
        assert passed, f"Should pass but failed: {reason}"

    def test_generic_acquisition_question(self):
        sq = sanitize(_ACQUISITION_QUERY)
        passed, reason = check_fragment_deterministic(
            "How are earnout structures typically designed in technology company acquisitions?",
            sq,
        )
        assert passed, f"Should pass but failed: {reason}"

    def test_generic_security_question(self):
        sq = sanitize(_JWT_QUERY)
        passed, reason = check_fragment_deterministic(
            "What is the best practice for rotating authentication secrets without causing service downtime?",
            sq,
        )
        assert passed, f"Should pass but failed: {reason}"

    def test_generic_harassment_question(self):
        sq = sanitize(_HARASSMENT_QUERY)
        passed, reason = check_fragment_deterministic(
            "What are the legal protections for employees who report workplace misconduct?",
            sq,
        )
        assert passed, f"Should pass but failed: {reason}"

    def test_generic_medical_question(self):
        sq = sanitize(
            "I'm a 34-year-old pilot at Delta and just got diagnosed with "
            "type 1 diabetes. Will I lose my medical certificate?"
        )
        passed, reason = check_fragment_deterministic(
            "What are the general requirements for maintaining professional certifications when health conditions change?",
            sq,
        )
        assert passed, f"Should pass but failed: {reason}"


# ---------------------------------------------------------------------------
# Async check_fragment (no LLM judge)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_fragment_returns_safe_fragment():
    sq = sanitize(_ACME_QUERY)
    result = await check_fragment(
        "What legal options exist when a business partner threatens to take proprietary work?",
        sq,
        llm_judge=None,
    )
    assert result.passed
    assert result.fragment is not None
    assert isinstance(result.fragment, SafeFragment)


@pytest.mark.asyncio
async def test_check_fragment_rejects_leaked():
    sq = sanitize(_ACME_QUERY)
    result = await check_fragment(
        "What should Acme do?", sq, llm_judge=None,
    )
    assert not result.passed
    assert result.fragment is None
