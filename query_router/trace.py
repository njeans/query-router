"""Pipeline trace for the presentation UI.

Runs each pipeline step individually and captures intermediate state.
Mock mode provides pre-canned data for offline presentations.
"""

from __future__ import annotations

from query_router.sanitize import sanitize, SanitizedQuery
from query_router.leak_check import check_fragment_deterministic

# ---------------------------------------------------------------------------
# Mock data for offline presentations
# ---------------------------------------------------------------------------

_FIXTURE_KEYWORDS: dict[str, list[str]] = {
    "pilot_diabetes": ["pilot", "diabetes"],
    "cofounder_ip": ["cofounder", "source code"],
    "acquisition": ["acquiring", "earnout"],
    "jwt_leak": ["jwt", "hs256"],
    "harassment_visa": ["harassment", "h-1b"],
}

_MOCK_FRAGMENTS: dict[str, list[str]] = {
    "pilot_diabetes": [
        "What are the requirements for maintaining professional aviation certifications when a crew member develops a chronic medical condition?",
        "What considerations exist for disclosing a new health condition to an employer in a safety-critical industry?",
    ],
    "cofounder_ip": [
        "What legal protections exist for intellectual property when no formal assignment agreement was signed between business partners?",
        "What steps can someone take to prevent a departing business partner from taking proprietary software?",
    ],
    "acquisition": [
        "What are common strategies for structuring earnout agreements when acquiring a technology company?",
        "How can acquiring companies retain key technical leadership after completing a merger?",
    ],
    "jwt_leak": [
        "What are the security implications of using symmetric signing algorithms for authentication tokens?",
        "How can an organization rotate compromised cryptographic secrets without causing service downtime?",
    ],
    "harassment_visa": [
        "What legal protections exist for employees who want to report workplace harassment?",
        "How does employment-based immigration status affect an employee's ability to report workplace misconduct?",
    ],
}

_DEFAULT_FRAGMENTS = [
    "What are the general considerations in this type of situation?",
    "What steps should someone take to protect their interests?",
]

_MOCK_REMOTE_ANSWERS: dict[str, list[str]] = {
    "pilot_diabetes": [
        "Aviation medical certifications are governed by regulatory bodies like the FAA. A new chronic condition typically requires disclosure at the next medical examination. Special Issuance certificates may allow continued flying with proper documentation and ongoing monitoring.",
        "In safety-sensitive industries, early disclosure is generally recommended. Many jurisdictions have legal protections against medical discrimination. Consulting with both a medical professional and an employment attorney before disclosure can help protect your rights.",
    ],
    "cofounder_ip": [
        "Without a formal IP assignment, ownership depends on jurisdiction and the business relationship. Code created as part of business operations may be company property under trade secret law, but enforcement is harder without written agreements.",
        "To protect proprietary software: document all contributions and access logs, implement repository access controls, send a formal cease-and-desist if needed, and consult an IP attorney about injunctive relief.",
    ],
    "acquisition": [
        "Common earnout structures include milestone-based payments tied to revenue targets or product goals. Typical earnout periods range from 1-3 years. Key considerations include clearly defining metrics and ensuring operational autonomy.",
        "Retaining key technical leadership post-acquisition typically involves retention bonuses, accelerated vesting, earnout participation, and meaningful influence over product direction and technology roadmap.",
    ],
    "jwt_leak": [
        "Symmetric algorithms mean anyone with the secret can forge tokens. If exposed publicly, all previously issued tokens should be considered compromised. Attackers could gain full administrative access to any system trusting those tokens.",
        "To rotate without downtime: deploy the new secret alongside the old one, issue new tokens with the new secret, wait for old tokens to expire, then remove the old secret. Consider switching to asymmetric algorithms.",
    ],
    "harassment_visa": [
        "Federal and state laws protect all employees from workplace harassment regardless of immigration status. Title VII and EEOC guidance apply equally. Employers cannot retaliate against employees who report harassment in good faith.",
        "Employment-based visa holders have the same workplace protections as other employees. If terminated as retaliation, visa holders may be eligible for grace periods to find new sponsorship. Consulting both an employment and immigration attorney is advisable.",
    ],
}

_DEFAULT_REMOTE_ANSWERS = [
    "General guidance depends on the specific circumstances and jurisdiction. Consulting with a qualified professional is recommended.",
    "Several protective steps can be taken. Documentation, legal counsel, and understanding applicable regulations are key starting points.",
]

_MOCK_FINAL_ANSWERS: dict[str, str] = {
    "pilot_diabetes": (
        "Given your situation as a [AGE_1] [JOB_TITLE_1] at [COMPANY_1] with a new [MEDICAL_1] diagnosis:\n\n"
        "**Medical Certificate:** You will need to disclose [MEDICAL_1] at your next FAA medical examination. "
        "This does not necessarily mean losing your certificate \u2014 the FAA offers Special Issuance certificates "
        "for well-managed conditions. You'll need documentation showing stable management from your physician.\n\n"
        "**Disclosure to HR:** As a [AGE_1] [JOB_TITLE_1], early disclosure is generally recommended in safety-sensitive roles. "
        "You have legal protections under the ADA against discrimination. However, consult with both your aviation medical "
        "examiner and an employment attorney before your next check ride to understand your specific rights and obligations."
    ),
    "cofounder_ip": (
        "Regarding the situation at [COMPANY_1] with your [JOB_TITLE_1]:\n\n"
        "**IP Ownership:** Without a signed IP assignment agreement, ownership of the source code depends on your jurisdiction "
        "and business structure. Code created as part of company operations is likely company property under trade secret law, "
        "but proving this is harder without formal documentation.\n\n"
        "**Immediate Steps:**\n"
        "1. Document all code contributions and access logs\n"
        "2. Restrict repository access immediately\n"
        "3. Send a formal cease-and-desist letter\n"
        "4. Consult an IP attorney about injunctive relief\n\n"
        "**Long-term:** Ensure all current and future team members sign IP assignment agreements."
    ),
    "acquisition": (
        "For the proposed acquisition:\n\n"
        "**Earnout Structure:** Consider milestone-based payments tied to revenue targets, customer retention, "
        "or product development goals over a 1-3 year period. Define metrics clearly and include dispute resolution mechanisms. "
        "Ensure the acquired team retains enough operational autonomy to realistically achieve the targets.\n\n"
        "**Retaining the [JOB_TITLE_1]:** Use a combination of financial incentives (retention bonus, accelerated vesting, "
        "earnout participation) and meaningful role definition. The most successful approaches give technical leaders "
        "genuine influence over product direction and the technology roadmap."
    ),
    "jwt_leak": (
        "This is a **critical security incident** that needs immediate attention.\n\n"
        "**Severity:** Since [TECH_1] is a symmetric algorithm, anyone with the exposed secret can forge valid tokens "
        "with arbitrary claims \u2014 including admin access. All tokens issued with this secret should be considered compromised.\n\n"
        "**Zero-Downtime Rotation:**\n"
        "1. Generate a new signing secret\n"
        "2. Deploy your API to accept tokens signed with either the old or new secret\n"
        "3. Issue all new tokens with the new secret only\n"
        "4. Wait for the maximum token lifetime to elapse\n"
        "5. Remove the old secret from your verification logic\n\n"
        "**Also:** Rotate the exposed secret in your GitHub repo, audit access logs, and consider migrating to asymmetric "
        "algorithms (RS256/ES256) where the verification key can safely be public."
    ),
    "harassment_visa": (
        "You have strong legal protections in this situation:\n\n"
        "**Reporting Rights:** Federal and state laws protect all employees from workplace harassment, regardless of "
        "immigration status. [PERSON_1]'s behavior (after-hours meetings, appearance comments) likely constitutes harassment. "
        "You can report to HR, the EEOC, or your state's fair employment agency.\n\n"
        "**[VISA_TYPE_1] Protections:** Your [VISA_TYPE_1] status does not limit your right to report misconduct. "
        "Employers are prohibited from using immigration status as retaliation. If terminated in retaliation, "
        "you may have a grace period to find new sponsorship, and additional legal remedies.\n\n"
        "**Recommended Steps:** Document all incidents with dates and details. Consult with both an employment attorney "
        "and an immigration attorney before filing a formal complaint to ensure your rights are fully protected."
    ),
}

_DEFAULT_FINAL_ANSWER = (
    "Based on the research gathered, here is a comprehensive answer to your question. "
    "The specific details depend on your jurisdiction and circumstances. "
    "Consulting with a qualified professional is recommended for advice tailored to your situation."
)


# ---------------------------------------------------------------------------
# Fixture matching
# ---------------------------------------------------------------------------

def _identify_fixture(query: str) -> str | None:
    q = query.lower()
    for name, keywords in _FIXTURE_KEYWORDS.items():
        if all(kw in q for kw in keywords):
            return name
    return None


# ---------------------------------------------------------------------------
# Pipeline trace
# ---------------------------------------------------------------------------

async def trace(query: str, mock: bool = True) -> dict:
    """Run the pipeline step by step, returning all intermediate state.

    In mock mode, decomposition/remote/recombine use pre-canned data.
    Sanitization and deterministic leak checks always run for real.
    """
    fixture = _identify_fixture(query)

    # Step 1: Sanitize (always real - regex-based, no LLM)
    sanitized = sanitize(query)

    # Step 2: Decompose
    if mock:
        fragments = _MOCK_FRAGMENTS.get(fixture, _DEFAULT_FRAGMENTS)
    else:
        try:
            from query_router.decompose import decompose
            fragments = await decompose(sanitized)
        except Exception as e:
            fragments = []

    # Step 3: Leak check (always real - deterministic)
    leak_results = []
    for frag in fragments:
        passed, reason = check_fragment_deterministic(frag, sanitized)
        leak_results.append({"text": frag, "passed": passed, "reason": reason})

    safe_fragments = [r["text"] for r in leak_results if r["passed"]]

    # Step 4: Remote answers
    if mock:
        answers = _MOCK_REMOTE_ANSWERS.get(fixture, _DEFAULT_REMOTE_ANSWERS)
        remote_exchanges = [
            {"sent": frag, "response": answers[i] if i < len(answers) else "General answer."}
            for i, frag in enumerate(safe_fragments)
        ]
    else:
        remote_exchanges = [
            {"sent": frag, "response": "(live Darkbloom response)"}
            for frag in safe_fragments
        ]

    # Step 5: Recombine
    if mock:
        answer_with_placeholders = _MOCK_FINAL_ANSWERS.get(fixture, _DEFAULT_FINAL_ANSWER)
    else:
        answer_with_placeholders = "(live recombined answer)"

    # Substitute placeholders for the final display
    final_answer = answer_with_placeholders
    for placeholder, value in sanitized.placeholder_map.mapping.items():
        final_answer = final_answer.replace(placeholder, value)

    return {
        "query": query,
        "sanitized_text": sanitized.text,
        "placeholder_map": sanitized.placeholder_map.mapping,
        "fragments": fragments,
        "leak_checks": leak_results,
        "safe_count": len(safe_fragments),
        "remote_exchanges": remote_exchanges,
        "answer_with_placeholders": answer_with_placeholders,
        "final_answer": final_answer,
        "tier": "split" if safe_fragments else "local_fallback",
    }
