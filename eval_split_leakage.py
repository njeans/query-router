#!/usr/bin/env python3
"""
Evaluation script: measure how much an adversary can reconstruct from fragments.

For each fixture, runs the pipeline (with mocked remote calls), then gives an
adversary LLM only the fragments and asks it to reconstruct the original
question and every specific entity. Reports a markdown table.

Usage:
    python eval_split_leakage.py          # uses Tinfoil LLM
    python eval_split_leakage.py --mock   # uses mock decomposition (no LLM needed)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys

from query_router.leak_check import SafeFragment
from query_router.remote import RemoteAnswer
from query_router.router import route
from query_router.sanitize import sanitize

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


class MockRemoteSender:
    def __init__(self):
        self.calls: list[SafeFragment] = []

    async def __call__(self, fragment: SafeFragment) -> RemoteAnswer:
        self.calls.append(fragment)
        return RemoteAnswer(
            fragment_text=fragment.text,
            answer=f"General answer about: {fragment.text}",
        )


async def adversary_reconstruct(fragments: list[str], use_llm: bool) -> list[str]:
    """Have an adversary try to reconstruct entities from fragments."""
    if not use_llm or not fragments:
        return []

    from query_router import local_llm, prompts

    numbered = "\n".join(f"{i+1}. {f}" for i, f in enumerate(fragments))
    prompt = prompts.CROSS_FRAGMENT_ADVERSARY.format(fragments=numbered)
    messages = [{"role": "user", "content": prompt}]

    try:
        result = await local_llm.chat_json(messages, temperature=0.0)
        if isinstance(result, list):
            return [str(x) for x in result]
    except Exception:
        pass
    return []


async def evaluate_fixture(
    name: str,
    query: str,
    use_llm: bool,
) -> dict:
    """Evaluate a single fixture. Returns metrics dict."""
    sq = sanitize(query)
    entities = sq.placeholder_map.values
    mock_sender = MockRemoteSender()

    result = await route(
        query,
        use_llm_sanitize=use_llm,
        use_llm_judges=use_llm,
        remote_send_fn=mock_sender,
    )

    fragments_sent = [f.text for f in mock_sender.calls]
    n_fragments = len(fragments_sent)
    is_fallback = result.tier == "local_fallback"

    # Adversary reconstruction
    if use_llm and fragments_sent:
        guesses = await adversary_reconstruct(fragments_sent, use_llm=True)
    else:
        guesses = []

    # Count recovered entities
    recovered = 0
    for entity in entities:
        entity_lower = entity.lower()
        for guess in guesses:
            guess_lower = guess.lower().strip()
            if entity_lower == guess_lower or (
                len(guess_lower) >= 3 and guess_lower in entity_lower
            ):
                recovered += 1
                break

    recovery_pct = (recovered / len(entities) * 100) if entities else 0

    return {
        "name": name,
        "n_entities": len(entities),
        "n_fragments": n_fragments,
        "recovered": recovered,
        "recovery_pct": recovery_pct,
        "fallback": is_fallback,
        "fragments": fragments_sent,
        "guesses": guesses,
    }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="Use mock decomposition (no LLM)")
    args = parser.parse_args()

    use_llm = not args.mock

    if args.mock:
        # Patch decompose and recombine/fallback to avoid LLM
        import query_router.router as router_mod

        async def mock_decompose(sq, retry_reason=None):
            return [
                "What are the general legal considerations in this type of situation?",
                "What steps should someone take to protect their interests?",
            ]

        async def mock_fallback(q):
            return "Local fallback answer."

        async def mock_recombine(sq, fas):
            return "Mock recombined answer."

        router_mod.decompose = mock_decompose
        router_mod.local_fallback = mock_fallback
        router_mod.recombine = mock_recombine

    results = []
    for name, query in FIXTURES:
        try:
            r = await evaluate_fixture(name, query, use_llm=use_llm)
            results.append(r)
        except Exception as e:
            results.append({
                "name": name,
                "n_entities": 0,
                "n_fragments": 0,
                "recovered": 0,
                "recovery_pct": 0,
                "fallback": True,
                "fragments": [],
                "guesses": [],
                "error": str(e),
            })

    # Print markdown table
    print()
    print("## Split Leakage Evaluation")
    print()
    print("| Fixture | Entities | Fragments | Recovered | Recovery % | Fallback |")
    print("|---------|----------|-----------|-----------|------------|----------|")

    total_entities = 0
    total_recovered = 0
    total_fallback = 0

    for r in results:
        fb = "yes" if r["fallback"] else "no"
        err = f' (err: {r.get("error", "")})' if "error" in r else ""
        print(
            f"| {r['name']} | {r['n_entities']} | {r['n_fragments']} | "
            f"{r['recovered']} | {r['recovery_pct']:.0f}% | {fb}{err} |"
        )
        total_entities += r["n_entities"]
        total_recovered += r["recovered"]
        if r["fallback"]:
            total_fallback += 1

    overall_pct = (total_recovered / total_entities * 100) if total_entities else 0
    fallback_rate = total_fallback / len(results) * 100

    print(f"| **TOTAL** | {total_entities} | — | {total_recovered} | "
          f"{overall_pct:.0f}% | {fallback_rate:.0f}% |")
    print()

    if not use_llm:
        print("_Note: Run without --mock for adversary LLM reconstruction._")
    print()


if __name__ == "__main__":
    asyncio.run(main())
