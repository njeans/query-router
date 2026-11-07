"""
Orchestration: sanitize → decompose → leak-check → remote → recombine.
Fail-closed: if leak check fails twice, answer with Tinfoil only (no splitting).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List

from query_router import local_llm, prompts
from query_router.decompose import DecompositionError, decompose
from query_router.leak_check import (
    LeakCheckResult,
    SafeFragment,
    check_fragment,
    cross_fragment_check,
)
from query_router.recombine import local_fallback, recombine
from query_router.remote import RemoteAnswer, send as remote_send
from query_router.sanitize import SanitizedQuery, sanitize, sanitize_with_llm_entities


@dataclass
class RouterResult:
    answer: str
    tier: str  # "split" or "local_fallback"
    fragments_sent: List[str] = field(default_factory=list)
    fragment_answers: List[RemoteAnswer] = field(default_factory=list)
    fallback_reason: str | None = None


# ---------------------------------------------------------------------------
# LLM judge helpers
# ---------------------------------------------------------------------------

async def _llm_leak_judge(fragment_text: str) -> bool:
    """Ask Tinfoil LLM if a fragment could identify a specific person/org/situation."""
    prompt = prompts.LEAK_JUDGE.format(fragment=fragment_text)
    messages = [{"role": "user", "content": prompt}]
    resp = await local_llm.chat(messages, temperature=0.0, max_tokens=10)
    return resp.strip().lower().startswith("yes")


async def _llm_cross_judge(fragment_texts: list[str]) -> list[str]:
    """Ask Tinfoil LLM to reconstruct entities from fragments."""
    numbered = "\n".join(f"{i+1}. {f}" for i, f in enumerate(fragment_texts))
    prompt = prompts.CROSS_FRAGMENT_ADVERSARY.format(fragments=numbered)
    messages = [{"role": "user", "content": prompt}]
    try:
        result = await local_llm.chat_json(messages, temperature=0.0)
        if isinstance(result, list):
            return [str(x) for x in result]
    except Exception:
        pass
    return []


async def _detect_entities_llm(query: str) -> list[tuple[str, str]]:
    """Use Tinfoil LLM to detect entities for sanitization."""
    prompt = prompts.ENTITY_DETECTION.format(query=query)
    messages = [{"role": "user", "content": prompt}]
    try:
        result = await local_llm.chat_json(messages, temperature=0.0)
        if isinstance(result, list):
            return [(e["category"], e["value"]) for e in result if "category" in e and "value" in e]
    except Exception:
        pass
    return []


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

async def route(
    query: str,
    use_llm_sanitize: bool = True,
    use_llm_judges: bool = True,
    remote_send_fn=None,
) -> RouterResult:
    """Run the full split-and-route pipeline.

    remote_send_fn: override for testing (default: remote.send).
    """
    send_fn = remote_send_fn or remote_send

    # Step 1: Sanitize
    llm_entities = None
    if use_llm_sanitize:
        try:
            llm_entities = await _detect_entities_llm(query)
        except Exception:
            llm_entities = None

    sanitized = sanitize_with_llm_entities(query, llm_entities)

    # Step 2 + 3: Decompose & leak-check (with one retry)
    leak_judge = _llm_leak_judge if use_llm_judges else None
    cross_judge = _llm_cross_judge if use_llm_judges else None

    for attempt in range(2):
        try:
            retry_reason = None if attempt == 0 else last_failure_reason
            fragments_text = await decompose(sanitized, retry_reason=retry_reason)
        except DecompositionError as e:
            last_failure_reason = str(e)
            continue

        # Leak-check each fragment
        safe_fragments: list[SafeFragment] = []
        all_passed = True
        last_failure_reason = ""

        for frag_text in fragments_text:
            result: LeakCheckResult = await check_fragment(
                frag_text, sanitized, llm_judge=leak_judge,
            )
            if result.passed and result.fragment:
                safe_fragments.append(result.fragment)
            else:
                all_passed = False
                last_failure_reason = result.reason or "Unknown leak check failure"
                break

        if not all_passed:
            continue

        # Cross-fragment check
        cross_ok, cross_reason = await cross_fragment_check(
            safe_fragments, sanitized, llm_cross_judge=cross_judge,
        )
        if not cross_ok:
            last_failure_reason = cross_reason or "Cross-fragment check failed"
            continue

        # All checks passed — send fragments remotely
        remote_answers: list[RemoteAnswer] = []
        for sf in safe_fragments:
            answer = await send_fn(sf)
            remote_answers.append(answer)

        # Recombine
        final_answer = await recombine(sanitized, remote_answers)

        return RouterResult(
            answer=final_answer,
            tier="split",
            fragments_sent=[sf.text for sf in safe_fragments],
            fragment_answers=remote_answers,
        )

    # FAIL CLOSED: two attempts failed, use Tinfoil directly (no splitting)
    fallback_answer = await local_fallback(query)
    return RouterResult(
        answer=fallback_answer,
        tier="local_fallback",
        fallback_reason=last_failure_reason,
    )
