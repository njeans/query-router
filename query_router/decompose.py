"""
Decompose a sanitized query into 2–3 self-contained, generic sub-questions
using Tinfoil confidential inference.
"""

from __future__ import annotations

import json

from query_router import local_llm, prompts
from query_router.sanitize import SanitizedQuery


class DecompositionError(Exception):
    pass


async def decompose(
    sanitized_query: SanitizedQuery,
    retry_reason: str | None = None,
) -> list[str]:
    """Use the Tinfoil LLM to split the sanitized query into generic sub-questions.

    Returns a list of 2–3 question strings.
    Raises DecompositionError if the LLM output is invalid.
    """
    if retry_reason:
        prompt = prompts.DECOMPOSE_RETRY.format(
            reason=retry_reason,
            sanitized_query=sanitized_query.text,
        )
    else:
        prompt = prompts.DECOMPOSE.format(
            sanitized_query=sanitized_query.text,
        )

    messages = [{"role": "user", "content": prompt}]

    try:
        result = await local_llm.chat_json(messages, temperature=0.2)
    except (json.JSONDecodeError, Exception) as e:
        raise DecompositionError(f"LLM returned invalid JSON: {e}") from e

    if not isinstance(result, list):
        raise DecompositionError(f"Expected JSON array, got {type(result).__name__}")

    questions = [str(q).strip() for q in result if str(q).strip()]

    if len(questions) < 2 or len(questions) > 3:
        raise DecompositionError(
            f"Expected 2-3 sub-questions, got {len(questions)}"
        )

    return questions
