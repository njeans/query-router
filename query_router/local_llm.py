"""
Client for Near AI confidential inference (TEE-backed).
All sensitive processing happens through attested open-source models with
end-to-end encryption — data is protected by verified secure enclaves
even though inference runs remotely.
"""

from __future__ import annotations

import json
import os
import re


def _api_key() -> str:
    return os.environ.get("NEARAI_API_KEY", "")


def _model() -> str:
    return os.environ.get("NEARAI_MODEL", "z-ai/glm-5.3-flash")


async def chat(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 2048,
    model: str | None = None,
) -> str:
    """Send a chat completion to Near AI (attested, e2ee) and return the text."""
    from nearai_inference_sdk import InferenceClient

    async with InferenceClient(_api_key(), e2ee=True) as client:
        resp = await client.chat.completions.create(
            model=model or _model(),
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content


async def chat_json(
    messages: list[dict],
    temperature: float = 0.1,
    max_tokens: int = 2048,
    model: str | None = None,
) -> dict | list:
    """Chat and parse JSON from the response.

    Tries to extract JSON from markdown code fences if present.
    """
    raw = await chat(messages, temperature=temperature, max_tokens=max_tokens, model=model)
    # Try to extract JSON from code fences
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    text = fence_match.group(1).strip() if fence_match else raw.strip()
    return json.loads(text)
