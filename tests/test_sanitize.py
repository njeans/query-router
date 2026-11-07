"""Tests for the sanitization module."""

from query_router.sanitize import PlaceholderMap, SanitizedQuery, sanitize


def test_sanitize_pilot_diabetes():
    sq = sanitize(
        "I'm a 34-year-old pilot at Delta and just got diagnosed with "
        "type 1 diabetes. Will I lose my medical certificate, and should "
        "I tell HR before my next check ride?"
    )
    assert isinstance(sq, SanitizedQuery)
    # Key entities should be replaced
    assert "Delta" not in sq.text
    assert "34-year-old" not in sq.text
    assert "type 1 diabetes" not in sq.text.lower() or "[MEDICAL_" in sq.text
    assert "pilot" not in sq.text.lower() or "[JOB_TITLE_" in sq.text
    # Placeholders should be present
    assert "[" in sq.text and "]" in sq.text
    assert len(sq.placeholder_map) > 0


def test_sanitize_cofounder_ip():
    sq = sanitize(
        "My cofounder at Acme Robotics is threatening to leave with our "
        "source code. We never signed an IP assignment. What can I do?"
    )
    assert "Acme" not in sq.text
    assert "Acme Robotics" not in sq.text
    assert "[COMPANY_" in sq.text


def test_sanitize_acquisition():
    sq = sanitize(
        "We're considering acquiring a 40-person fintech in Austin at "
        "around $60M. How should we structure earnouts to keep their CTO?"
    )
    assert "Austin" not in sq.text
    assert "$60M" not in sq.text
    assert "CTO" not in sq.text.upper() or "[JOB_TITLE_" in sq.text


def test_sanitize_jwt_leak():
    sq = sanitize(
        "Our production API at api.example.com uses JWTs signed with "
        "HS256 and the secret is in a public GitHub repo. How bad is "
        "this and how do we rotate without downtime?"
    )
    assert "api.example.com" not in sq.text
    assert "HS256" not in sq.text or "[TECH_" in sq.text


def test_sanitize_harassment_visa():
    sq = sanitize(
        "My manager Sarah keeps scheduling 1:1s after hours and "
        "commenting on my appearance. I'm on an H-1B. Can I report "
        "this without risking my visa?"
    )
    assert "Sarah" not in sq.text
    assert "H-1B" not in sq.text or "[VISA_TYPE_" in sq.text


def test_placeholder_map_dedup():
    """Same value added twice should return the same placeholder."""
    pmap = PlaceholderMap()
    p1 = pmap.add("PERSON", "Sarah")
    p2 = pmap.add("PERSON", "Sarah")
    assert p1 == p2
    assert len(pmap) == 1


def test_placeholder_map_repr():
    pmap = PlaceholderMap()
    pmap.add("PERSON", "Sarah")
    assert "1 entries" in repr(pmap)
