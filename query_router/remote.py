"""
Darkbloom remote client. Accepts ONLY SafeFragment, never raw strings.
Each request uses a new httpx client, random jitter, no shared conversation.
"""

from __future__ import annotations

import asyncio
import os
import random
from dataclasses import dataclass

import httpx

from query_router.leak_check import SafeFragment


def _base_url() -> str:
    return os.environ.get("DARKBLOOM_BASE_URL", "https://api.darkbloom.dev/v1")


def _api_key() -> str:
    key = os.environ.get("DARKBLOOM_API_KEY", "")
    if not key:
        raise RuntimeError("DARKBLOOM_API_KEY environment variable is required")
    return key


def _model() -> str:
    model = os.environ.get("DARKBLOOM_MODEL", "")
    if not model:
        raise RuntimeError("DARKBLOOM_MODEL environment variable is required")
    return model


@dataclass
class RemoteAnswer:
    fragment_text: str
    answer: str


async def validate_model() -> None:
    """Check that DARKBLOOM_MODEL is listed at GET /models. Fail clearly if not."""
    base = _base_url()
    model = _model()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{base}/models",
            headers={"Authorization": f"Bearer {_api_key()}"},
        )
        resp.raise_for_status()
        data = resp.json()
        model_ids = [m["id"] for m in data.get("data", [])]
        if model not in model_ids:
            raise RuntimeError(
                f"DARKBLOOM_MODEL='{model}' not found in available models: {model_ids}"
            )


async def send(fragment: SafeFragment) -> RemoteAnswer:
    """Send a single SafeFragment to Darkbloom and return the answer.

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
            f"{_base_url()}/chat/completions",
            headers={
                "Authorization": f"Bearer {_api_key()}",
                "Content-Type": "application/json",
            },
            json={
                "model": _model(),
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
