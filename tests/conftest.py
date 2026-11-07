import pytest

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


@pytest.fixture(params=FIXTURES, ids=[f[0] for f in FIXTURES])
def fixture_query(request):
    """Yields (name, query_text) for each test fixture."""
    return request.param
