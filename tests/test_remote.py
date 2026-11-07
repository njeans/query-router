"""Tests for the remote module — type enforcement and mock tests."""

import pytest

from query_router.leak_check import SafeFragment, _create_safe_fragment
from query_router.remote import send


@pytest.mark.asyncio
async def test_remote_send_rejects_plain_str():
    """remote.send must reject a plain string — only SafeFragment allowed."""
    with pytest.raises(TypeError, match="SafeFragment"):
        await send("this is a plain string")  # type: ignore


@pytest.mark.asyncio
async def test_remote_send_rejects_dict():
    with pytest.raises(TypeError, match="SafeFragment"):
        await send({"text": "hello"})  # type: ignore


@pytest.mark.asyncio
async def test_remote_send_rejects_none():
    with pytest.raises(TypeError, match="SafeFragment"):
        await send(None)  # type: ignore
