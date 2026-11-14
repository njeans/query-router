"""
Near AI Incognito remote client. Accepts ONLY SafeFragment, never raw strings.
Each request uses a new httpx client, random jitter, no shared conversation.
Incognito models have gateway-only verification (no TEE attestation).
"""

from __future__ import annotations

import asyncio
import os
import random
from dataclasses import dataclass

import httpx

from query_router.leak_check import SafeFragment

_BASE_URL = "https://cloud-api.near.ai/v1"


def _api_key() -> str:
    key = os.environ.get("NEARAI_API_KEY", "")
    if not key:
        raise RuntimeError("NEARAI_API_KEY environment variable is required")
    return key


# Three default incognito models, each from a different provider so no single
# provider ever sees more than one fragment from the same query.
DEFAULT_INCOGNITO_MODELS: list[str] = [
    os.environ.get("NEARAI_INCOGNITO_MODEL_1", "google/gemini-2.0-flash"),
    os.environ.get("NEARAI_INCOGNITO_MODEL_2", "anthropic/claude-sonnet-4-6"),
    os.environ.get("NEARAI_INCOGNITO_MODEL_3", "openai/gpt-4.1-mini"),
]


@dataclass
class RemoteAnswer:
    fragment_text: str
    answer: str


async def validate_models(models: list[str] | None = None) -> None:
    """Check that all incognito models are listed at GET /models."""
    to_check = models or DEFAULT_INCOGNITO_MODELS
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{_BASE_URL}/models",
            headers={"Authorization": f"Bearer {_api_key()}"},
        )
        resp.raise_for_status()
        data = resp.json()
        model_ids = [m["id"] for m in data.get("data", [])]
        for m in to_check:
            if m not in model_ids:
                raise RuntimeError(
                    f"Incognito model '{m}' not found in available models: {model_ids}"
                )


async def send(fragment: SafeFragment, model: str | None = None) -> RemoteAnswer:
    """Send a single SafeFragment to Near AI Incognito and return the answer.

    - Type-enforced: only SafeFragment accepted, not str.
    - New httpx client per request.
    - Random jitter before sending.
    - No shared conversation or linking metadata.
    """
    if not isinstance(fragment, SafeFragment):
        raise TypeError(
            f"remote.send() accepts only SafeFragment, got {type(fragment).__name__}"
        )

    # Random jitter: 0.5–3s
    await asyncio.sleep(random.uniform(0.5, 3.0))

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {_api_key()}",
                "Content-Type": "application/json",
            },
            json={
                "model": model or DEFAULT_INCOGNITO_MODELS[0],
                "messages": [
                    {"role": "user", "content": fragment.text},
                ],
                "temperature": 0.3,
                "max_tokens": 1024,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        answer = data["choices"][0]["message"]["content"]

    return RemoteAnswer(fragment_text=fragment.text, answer=answer)
