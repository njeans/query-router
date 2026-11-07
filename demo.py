#!/usr/bin/env python3
"""
Demo: sends fixture 2 (cofounder IP) through the proxy and prints side by side:
- Original query
- Sanitized query
- Each fragment sent remotely
- Final answer

Usage:
    python demo.py          # needs Tinfoil API key + optionally Darkbloom
    python demo.py --mock   # fully mocked, no external services needed
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from query_router.leak_check import SafeFragment
from query_router.remote import RemoteAnswer
from query_router.router import route
from query_router.sanitize import sanitize


QUERY = (
    "My cofounder at Acme Robotics is threatening to leave with our source code. "
    "We never signed an IP assignment. What can I do?"
)


class MockRemoteSender:
    def __init__(self):
        self.calls = []

    async def __call__(self, fragment: SafeFragment) -> RemoteAnswer:
        self.calls.append(fragment)
        # Simulate a realistic-looking answer
        answers = {
            0: (
                "When no formal intellectual property agreement exists between "
                "business partners, the default rules of trade secret law and "
                "copyright generally apply. Code written by an employee is typically "
                "owned by the employer under work-for-hire doctrine, but for "
                "co-founders the situation is murkier. You should consult an IP "
                "attorney immediately."
            ),
            1: (
                "To protect proprietary code when a partner threatens to leave: "
                "1) Document all contributions and access logs. "
                "2) Send a formal cease-and-desist letter. "
                "3) Consider filing for a temporary restraining order if theft is imminent. "
                "4) Implement access controls immediately. "
                "5) Consult with a business litigation attorney."
            ),
        }
        idx = len(self.calls) - 1
        answer = answers.get(idx, "General legal advice would apply here.")
        return RemoteAnswer(fragment_text=fragment.text, answer=answer)


def print_section(title: str, content: str):
    width = 72
    print(f"\n{'=' * width}")
    print(f"  {title}")
    print(f"{'=' * width}")
    print(content)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="Use mocked services")
    args = parser.parse_args()

    mock_sender = MockRemoteSender() if args.mock else None

    if args.mock:
        import query_router.router as router_mod

        async def mock_decompose(sq, retry_reason=None):
            return [
                "What legal protections exist for intellectual property when no formal agreement was signed between business partners?",
                "What steps can someone take to prevent a departing business partner from taking proprietary code?",
            ]

        async def mock_fallback(q):
            return "Consult an IP attorney immediately."

        async def mock_recombine(sq, fas):
            qa = "\n".join(f"Q: {a.fragment_text}\nA: {a.answer}" for a in fas)
            return (
                f"Based on research, here is advice for the situation with "
                f"{sq.placeholder_map.mapping.get('[COMPANY_1]', 'your company')}:\n\n"
                f"Since no IP assignment was signed with your "
                f"{sq.placeholder_map.mapping.get('[JOB_TITLE_1]', 'partner')}, "
                f"the legal situation depends on several factors. Code written as "
                f"part of the business is likely company property under trade secret "
                f"law, but without a formal agreement this is harder to enforce.\n\n"
                f"Immediate steps:\n"
                f"1. Document all contributions and access logs\n"
                f"2. Restrict repository access immediately\n"
                f"3. Send a formal cease-and-desist letter\n"
                f"4. Consult an IP attorney for jurisdiction-specific advice\n"
                f"5. Consider filing for injunctive relief if theft is imminent\n\n"
                f"Long-term: ensure all current and future team members sign IP "
                f"assignment agreements."
            )

        router_mod.decompose = mock_decompose
        router_mod.local_fallback = mock_fallback
        router_mod.recombine = mock_recombine

    # Run the pipeline
    print_section("ORIGINAL QUERY", QUERY)

    sq = sanitize(QUERY)
    print_section("SANITIZED QUERY", sq.text)
    print(f"\n  Placeholders: {sq.placeholder_map.mapping}")

    if args.mock:
        result = await route(
            QUERY,
            use_llm_sanitize=False,
            use_llm_judges=False,
            remote_send_fn=mock_sender,
        )
    else:
        result = await route(QUERY)

    print_section("TIER", result.tier)

    if result.fragments_sent:
        for i, frag in enumerate(result.fragments_sent, 1):
            print_section(f"FRAGMENT {i} (sent to Darkbloom)", frag)
            if i <= len(result.fragment_answers):
                print(f"\n  Response: {result.fragment_answers[i-1].answer[:200]}...")
    else:
        print("\n  (No fragments sent — Tinfoil fallback)")

    if result.fallback_reason:
        print_section("FALLBACK REASON", result.fallback_reason)

    print_section("FINAL ANSWER", result.answer)


if __name__ == "__main__":
    asyncio.run(main())
