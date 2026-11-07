"""
FastAPI server: OpenAI-compatible POST /v1/chat/completions
plus GET /provider-log for transparency and /ui for the presentation demo.
"""

from __future__ import annotations

import pathlib
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from query_router.router import RouterResult, route
from query_router.trace import trace as run_trace

app = FastAPI(title="Query Router – Tier 1 (Splittable)")

# Mount static files for the presentation UI
_static_dir = pathlib.Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=_static_dir), name="static")

# ---------------------------------------------------------------------------
# Provider log (in-memory only, never persists)
# ---------------------------------------------------------------------------

MAX_LOG_ENTRIES = 100


@dataclass
class ProviderLogEntry:
    request_id: str
    timestamp: float
    tier: str
    fragments_sent: List[str]
    fragment_responses: List[str]
    fallback_reason: str | None = None


_provider_log: deque[ProviderLogEntry] = deque(maxlen=MAX_LOG_ENTRIES)


# ---------------------------------------------------------------------------
# Request / Response models (OpenAI-compatible subset)
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "query-router"
    messages: List[ChatMessage]
    temperature: float = 0.7
    max_tokens: int = 2048


class Choice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str = "query-router"
    choices: List[Choice]
    tier: str
    fallback_reason: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest) -> ChatCompletionResponse:
    # Extract the latest user message
    user_messages = [m for m in req.messages if m.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found")

    query = user_messages[-1].content
    request_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

    # Route through the pipeline
    result: RouterResult = await route(query)

    # Log what was sent to Darkbloom (NEVER log original query or placeholder map)
    entry = ProviderLogEntry(
        request_id=request_id,
        timestamp=time.time(),
        tier=result.tier,
        fragments_sent=result.fragments_sent,
        fragment_responses=[fa.answer for fa in result.fragment_answers],
        fallback_reason=result.fallback_reason,
    )
    _provider_log.append(entry)

    return ChatCompletionResponse(
        id=request_id,
        created=int(time.time()),
        choices=[
            Choice(
                message=ChatMessage(role="assistant", content=result.answer),
            )
        ],
        tier=result.tier,
        fallback_reason=result.fallback_reason,
    )


@app.get("/provider-log")
async def provider_log():
    """Return recent provider interactions.

    Shows ONLY what was sent to Darkbloom and their responses.
    NEVER contains the original query or placeholder map.
    """
    return [
        {
            "request_id": e.request_id,
            "timestamp": e.timestamp,
            "tier": e.tier,
            "fragments_sent": e.fragments_sent,
            "fragment_responses": e.fragment_responses,
            "fallback_reason": e.fallback_reason,
        }
        for e in _provider_log
    ]


# ---------------------------------------------------------------------------
# Presentation UI
# ---------------------------------------------------------------------------

class TraceRequest(BaseModel):
    query: str
    mock: bool = True


@app.get("/ui")
async def ui():
    return RedirectResponse("/static/index.html")


@app.post("/api/trace")
async def trace_endpoint(req: TraceRequest):
    """Run the pipeline step by step and return all intermediate state."""
    return await run_trace(req.query, mock=req.mock)
