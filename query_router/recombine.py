"""
Recombine fragment answers into a final answer, then substitute placeholders back.
Processing uses Tinfoil confidential inference — the final answer is never
exposed to untrusted providers.
"""

from __future__ import annotations

from query_router import local_llm, prompts
from query_router.remote import RemoteAnswer
from query_router.sanitize import SanitizedQuery


async def recombine(
    sanitized_query: SanitizedQuery,
    fragment_answers: list[RemoteAnswer],
) -> str:
    """Synthesise a final answer from fragment Q&A pairs, then de-placeholder.

    1. Tinfoil LLM merges fragment answers using the sanitized query.
    2. Placeholders are replaced with real values from the map.
    """
    # Build fragment Q&A text
    qa_parts = []
    for i, fa in enumerate(fragment_answers, 1):
        qa_parts.append(f"Sub-question {i}: {fa.fragment_text}\nAnswer {i}: {fa.answer}")
    fragment_text = "\n\n".join(qa_parts)

    prompt = prompts.RECOMBINE.format(
        sanitized_query=sanitized_query.text,
        fragment_answers=fragment_text,
    )

    messages = [{"role": "user", "content": prompt}]
    raw_answer = await local_llm.chat(messages, temperature=0.3)

    # Substitute placeholders back to real values
    final_answer = _substitute_placeholders(raw_answer, sanitized_query)
    return final_answer


async def local_fallback(query: str) -> str:
    """Answer the query entirely with Tinfoil (no fragment splitting)."""
    prompt = prompts.LOCAL_FALLBACK.format(query=query)
    messages = [{"role": "user", "content": prompt}]
    return await local_llm.chat(messages, temperature=0.4)


def _substitute_placeholders(text: str, sanitized_query: SanitizedQuery) -> str:
    """Replace placeholder tokens with their original values."""
    result = text
    for placeholder, value in sanitized_query.placeholder_map.mapping.items():
        result = result.replace(placeholder, value)
    return result
