"""
Client for Tinfoil confidential inference (TEE-backed).
All sensitive processing happens through this client — data is protected
by verified secure enclaves even though inference runs remotely.
"""

from __future__ import annotations

import json
import os
import re

def _api_key() -> str:
    return os.environ.get("TINFOIL_API_KEY", "")


def _model() -> str:
    return os.environ.get("TINFOIL_MODEL", "llama3-3-70b")


async def chat(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> str:
    """Send a chat completion to Tinfoil and return the text."""
    from tinfoil import AsyncTinfoilAI

    client = AsyncTinfoilAI(api_key=_api_key())
    try:
        resp = await client.chat.completions.create(
            model=_model(),
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content
    finally:
        await client.close()


async def chat_json(
    messages: list[dict],
    temperature: float = 0.1,
    max_tokens: int = 2048,
) -> dict | list:
    """Chat and parse JSON from the response.

    Tries to extract JSON from markdown code fences if present.
    """
    raw = await chat(messages, temperature=temperature, max_tokens=max_tokens)
    # Try to extract JSON from code fences
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    text = fence_match.group(1).strip() if fence_match else raw.strip()
    return json.loads(text)
