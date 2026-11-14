# Query Sharding - Privacy-Preserving Query Proxy (Tier 1: Splittable)

A privacy-preserving OpenAI-compatible proxy that hides your query from untrusted inference by splitting it into generic, non-identifying sub-questions. Sensitive processing (sanitization, decomposition, leak checking, recombination) runs on [Near AI](https://near.ai) attested open-source models with end-to-end encryption — models execute in verified TEE enclaves so the operator cannot see your data. Generic sub-questions are routed to different Near AI Incognito models (gateway-only verification, no TEE attestation) so that no single provider ever sees more than one fragment.

## How It Works

1. **Sanitize** - Detects and replaces sensitive entities (names, companies, amounts, hostnames, etc.) with typed placeholders like `[PERSON_1]`, `[COMPANY_1]`
2. **Decompose** - Near AI attested LLM splits the sanitized query into 2-3 self-contained, generic sub-questions
3. **Leak Check** - Each fragment is verified against 6 layers of checks (value matching, placeholder patterns, numbers, PII regex backstop, LLM judge, cross-fragment adversary)
4. **Remote Send** - Each safe fragment is routed to a different Near AI Incognito model so no single provider sees more than one fragment. Requests use random jitter, no shared conversation, and no linking metadata
5. **Recombine** - The Near AI attested LLM merges the answers and substitutes placeholders back

The raw query, placeholder mapping, and final answer are only ever processed inside attested enclaves with e2ee — **never exposed to incognito providers**.

## Setup

```bash
# Install (requires Python 3.12+)
pip install -e ".[dev]"
```

No local model installation required — Near AI handles inference remotely. Attested models run in secure enclaves with end-to-end encryption.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NEARAI_API_KEY` | `""` | Near AI API key (used for both attested and incognito) |
| `NEARAI_MODEL` | `z-ai/glm-5.3-flash` | Attested model for trusted processing (e2ee) |
| `NEARAI_INCOGNITO_MODEL_1` | `google/gemini-2.0-flash` | Incognito model for fragment 1 (Google) |
| `NEARAI_INCOGNITO_MODEL_2` | `anthropic/claude-sonnet-4-6` | Incognito model for fragment 2 (Anthropic) |
| `NEARAI_INCOGNITO_MODEL_3` | `openai/gpt-4.1-mini` | Incognito model for fragment 3 (OpenAI) |

## Running the Server

```bash
# Set credentials
export NEARAI_API_KEY="your-nearai-key"
# Optionally override the three default incognito models:
# export NEARAI_INCOGNITO_MODEL_1="provider-a/model"
# export NEARAI_INCOGNITO_MODEL_2="provider-b/model"
# export NEARAI_INCOGNITO_MODEL_3="provider-c/model"

# Start the proxy
uvicorn query_router.server:app --host 0.0.0.0 --port 8000
```

## Pointing an OpenAI Client at It

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="unused")
response = client.chat.completions.create(
    model="query-router",
    messages=[{"role": "user", "content": "Your sensitive question here"}],
    extra_body={
        # Route each fragment to a different incognito model
        "models": ["model-a", "model-b", "model-c"],
    },
)
print(response.choices[0].message.content)
```

The `models` field is optional — if omitted, all fragments use `NEARAI_INCOGNITO_MODEL`.

## Endpoints

- `POST /v1/chat/completions` - OpenAI-compatible chat (non-streaming)
- `GET /provider-log` - Shows exactly what was sent to Incognito and their responses (never contains the original query or placeholder map)

## Running Tests

```bash
# Deterministic tests (no LLM needed)
pytest -m "not llm" -v

# Full tests including LLM integration (needs Near AI API key)
pytest -v
```

## Demo

```bash
# Fully mocked (no external services needed)
python demo.py --mock

# With live LLM (needs Near AI API key)
python demo.py
```

## Evaluation

```bash
# Mocked (no LLM needed)
python eval_split_leakage.py --mock

# With adversary LLM reconstruction (needs Near AI API key)
python eval_split_leakage.py
```

## Architecture

| Module | Role |
|--------|------|
| `sanitize.py` | PII detection (regex + optional LLM) and placeholder mapping |
| `leak_check.py` | 6-layer leak verification; `SafeFragment` type (only constructible here) |
| `decompose.py` | Near AI attested LLM splits sanitized query into generic sub-questions |
| `remote.py` | Near AI Incognito client; accepts only `SafeFragment`, never `str` |
| `recombine.py` | Near AI attested LLM merges fragment answers; substitutes placeholders back |
| `router.py` | Orchestration with retry, fail-closed fallback, and per-fragment model routing |
| `server.py` | FastAPI OpenAI-compatible endpoint |
| `prompts.py` | All LLM prompts in one place |
| `local_llm.py` | Client for Near AI attested inference (e2ee) |

## Threat Model

### What each Incognito provider sees

Each fragment is routed to a **different** incognito model, so no single provider ever sees more than one fragment from the same query. Each provider receives a single generic sub-question — e.g., "What are the general requirements for maintaining professional certifications when health conditions change?" — with **no** names, companies, amounts, hostnames, or other identifying details. Each request uses a fresh HTTP client, random jitter (0.5-3s), no shared conversation ID, and no metadata linking it to other fragments.

### What the Near AI gateway may see

The Near AI gateway routes all requests and could in principle correlate fragments by source IP or timing. The cross-fragment leak check mitigates this: it asks a Near AI attested LLM adversary to reconstruct identifying details from the combined fragments and rejects if it succeeds. However, this is a probabilistic defense — a more capable adversary model may succeed where the checked model fails.

### What Near AI attested models see

Near AI runs attested models inside TEE-backed secure enclaves (Intel TDX + NVIDIA confidential computing) with cryptographic attestation. The `nearai-inference-sdk` verifies enclave attestation and encrypts all communication end-to-end before sending data. With `e2ee=True`, the Gateway can route requests but **cannot** decrypt message content. This means the raw query, placeholder map, and final answer are confidential even though inference is remote.

### Attested vs Incognito

- **Attested models**: Full TEE attestation, e2ee support, hardware-verified isolation. Used for all sensitive processing (sanitization, decomposition, leak checking, recombination).
- **Incognito models**: Gateway-only verification, no TEE attestation claim. Used only for answering generic, de-identified sub-questions. Each fragment goes to a different incognito model, so even if one is compromised it sees only a single fragment that has passed the 6-layer leak check.

### Fragment separation across providers

The router accepts a list of three incognito model names and sends fragment *i* to model *i*. This ensures each fragment goes to a different provider. If no list is provided, all fragments fall back to the single `NEARAI_INCOGNITO_MODEL` default. Even with three distinct models, the Near AI gateway could correlate requests by source IP or timing — fragment separation is strongest when the models are hosted by independent backends.

### What the leak check does guarantee

- **Deterministic**: No fragment contains any placeholder map value (case-insensitive, partial-token matching), placeholder patterns, numbers from the original query, emails, URLs, hostnames, IPs, or phone numbers
- **LLM judge**: A Near AI attested model independently assesses each fragment for identifying potential
- **Cross-fragment**: A Near AI attested adversary model attempts reconstruction from all fragments combined

### What the leak check does NOT guarantee

- The LLM judge and cross-fragment adversary are limited by model capability — a stronger model could reconstruct more
- Semantic leakage (the *topic* of a question may narrow the population) is not fully prevented
- Side channels (timing, IP address, request patterns) are not addressed
- The regex/NER detection may miss novel entity formats not in its pattern set
- If Presidio is not installed, entity detection relies on regexes and a fixed name list

### Fail-closed behavior

If decomposition or leak checking fails twice, the system answers with the Near AI attested model only (no splitting). Zero fragments are sent to Incognito. The response is marked `"tier": "local_fallback"` with a reason.

## PII Detection Note

This implementation uses regex patterns and a curated entity list instead of Microsoft Presidio. For production use, install Presidio for more comprehensive PII detection:

```bash
pip install presidio-analyzer presidio-anonymizer
python -m spacy download en_core_web_lg
```
