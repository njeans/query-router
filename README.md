# Query Router - Privacy-Preserving Query Proxy (Tier 1: Splittable)

A privacy-preserving OpenAI-compatible proxy that hides your query from untrusted inference providers by splitting it into generic, non-identifying sub-questions. Sensitive processing (sanitization, decomposition, leak checking, recombination) runs on [Tinfoil](https://tinfoil.sh) confidential inference — models execute in verified secure enclaves (TEEs) so the operator cannot see your data.

## How It Works

1. **Sanitize** - Detects and replaces sensitive entities (names, companies, amounts, hostnames, etc.) with typed placeholders like `[PERSON_1]`, `[COMPANY_1]`
2. **Decompose** - Tinfoil LLM splits the sanitized query into 2-3 self-contained, generic sub-questions
3. **Leak Check** - Each fragment is verified against 6 layers of checks (value matching, placeholder patterns, numbers, PII regex backstop, LLM judge, cross-fragment adversary)
4. **Remote Send** - Safe fragments are sent to Darkbloom as separate requests with random jitter, no shared conversation, and no linking metadata
5. **Recombine** - The Tinfoil LLM merges the answers and substitutes placeholders back

The raw query, placeholder mapping, and final answer are only ever processed inside Tinfoil's verified enclaves — **never exposed to untrusted providers**.

## Setup

```bash
# Install
pip install -e ".[dev]"
```

No local model installation required — Tinfoil handles inference remotely in secure enclaves.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TINFOIL_API_KEY` | `""` | Tinfoil API key |
| `TINFOIL_MODEL` | `llama3-3-70b` | Tinfoil model name |
| `DARKBLOOM_BASE_URL` | `https://api.darkbloom.dev/v1` | Darkbloom API base |
| `DARKBLOOM_API_KEY` | (required) | Darkbloom API key |
| `DARKBLOOM_MODEL` | (required) | Darkbloom model name (validated against GET /models at startup) |

## Running the Server

```bash
# Set credentials
export TINFOIL_API_KEY="your-tinfoil-key"
export DARKBLOOM_API_KEY="your-darkbloom-key"
export DARKBLOOM_MODEL="your-model"

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
)
print(response.choices[0].message.content)
```

## Endpoints

- `POST /v1/chat/completions` - OpenAI-compatible chat (non-streaming)
- `GET /provider-log` - Shows exactly what was sent to Darkbloom and their responses (never contains the original query or placeholder map)

## Running Tests

```bash
# Deterministic tests (no LLM needed)
pytest -m "not llm" -v

# Full tests including LLM integration (needs Tinfoil API key)
pytest -v
```

## Demo

```bash
# Fully mocked (no external services needed)
python demo.py --mock

# With live LLM (needs Tinfoil API key)
python demo.py
```

## Evaluation

```bash
# Mocked (no LLM needed)
python eval_split_leakage.py --mock

# With adversary LLM reconstruction (needs Tinfoil API key)
python eval_split_leakage.py
```

## Architecture

| Module | Role |
|--------|------|
| `sanitize.py` | PII detection (regex + optional LLM) and placeholder mapping |
| `leak_check.py` | 6-layer leak verification; `SafeFragment` type (only constructible here) |
| `decompose.py` | Tinfoil LLM splits sanitized query into generic sub-questions |
| `remote.py` | Darkbloom client; accepts only `SafeFragment`, never `str` |
| `recombine.py` | Tinfoil LLM merges fragment answers; substitutes placeholders back |
| `router.py` | Orchestration with retry and fail-closed fallback |
| `server.py` | FastAPI OpenAI-compatible endpoint |
| `prompts.py` | All LLM prompts in one place |
| `local_llm.py` | Client for Tinfoil confidential inference |

## Threat Model

### What each Darkbloom provider sees

Each provider receives a single generic sub-question — e.g., "What are the general requirements for maintaining professional certifications when health conditions change?" — with **no** names, companies, amounts, hostnames, or other identifying details. Each request uses a fresh HTTP client, random jitter (0.5-3s), no shared conversation ID, and no metadata linking it to other fragments.

### What the Darkbloom coordinator may see

If Darkbloom routes all fragments through a single backend or logs by source IP, the coordinator can see **all fragments together**. The cross-fragment leak check mitigates this: it asks a Tinfoil LLM adversary to reconstruct identifying details from the combined fragments and rejects if it succeeds. However, this is a probabilistic defense — a more capable adversary model may succeed where the checked model fails.

### What Tinfoil sees

Tinfoil runs models inside TEE-backed secure enclaves with cryptographic attestation. The Tinfoil operator **cannot** read the data processed inside the enclave. The `tinfoil` Python SDK verifies enclave attestation before sending data, ensuring the enclave is running the expected code. This means the raw query, placeholder map, and final answer are confidential even though inference is remote.

### Fragment separation across providers is probabilistic

There is no mechanism to pin specific fragments to specific providers. If Darkbloom uses a single backend, all fragments are visible to the same entity. Fragment separation provides defense in depth only if Darkbloom actually distributes across independent providers.

### What the leak check does guarantee

- **Deterministic**: No fragment contains any placeholder map value (case-insensitive, partial-token matching), placeholder patterns, numbers from the original query, emails, URLs, hostnames, IPs, or phone numbers
- **LLM judge**: A Tinfoil model independently assesses each fragment for identifying potential
- **Cross-fragment**: A Tinfoil adversary model attempts reconstruction from all fragments combined

### What the leak check does NOT guarantee

- The LLM judge and cross-fragment adversary are limited by model capability — a stronger model could reconstruct more
- Semantic leakage (the *topic* of a question may narrow the population) is not fully prevented
- Side channels (timing, IP address, request patterns) are not addressed
- The regex/NER detection may miss novel entity formats not in its pattern set
- If Presidio is not installed, entity detection relies on regexes and a fixed name list

### Fail-closed behavior

If decomposition or leak checking fails twice, the system answers with the Tinfoil model only (no splitting). Zero fragments are sent to Darkbloom. The response is marked `"tier": "local_fallback"` with a reason.

## PII Detection Note

This implementation uses regex patterns and a curated entity list instead of Microsoft Presidio. For production use, install Presidio for more comprehensive PII detection:

```bash
pip install presidio-analyzer presidio-anonymizer
python -m spacy download en_core_web_lg
```
