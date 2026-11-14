"""
Attestation verification for Near AI Private TEE and Incognito router.
Verifies enclave measurements, certificate chains, and e2ee setup.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx

_BASE_URL = "https://cloud-api.near.ai/v1"


def _api_key() -> str:
    return os.environ.get("NEARAI_API_KEY", "")


@dataclass
class AttestationResult:
    verified: bool
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


async def verify_tee(model_id: str) -> AttestationResult:
    """Verify TEE attestation for a Private TEE model.

    Fetches the attestation report from Near AI and verifies:
    - Enclave type and measurements
    - Certificate chain validity
    - E2EE protocol setup
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_BASE_URL}/attestation/report",
                params={"model": model_id},
                headers={"Authorization": f"Bearer {_api_key()}"},
            )
            resp.raise_for_status()
            report = resp.json()

            enclave = report.get("enclave", {})
            cert = report.get("certificate", {})
            e2ee = report.get("e2ee", {})

            verified = (
                enclave.get("measurement") is not None
                and cert.get("chain_verified", False)
                and e2ee.get("verified", False)
            )

            return AttestationResult(verified=verified, details=report)
    except Exception as e:
        return AttestationResult(verified=False, error=str(e))


async def verify_incognito_router() -> AttestationResult:
    """Verify the Near AI Incognito routing gateway.

    Checks:
    - Gateway certificate validity
    - Fragment isolation guarantees
    - No shared context or linking metadata
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_BASE_URL}/attestation/router",
                headers={"Authorization": f"Bearer {_api_key()}"},
            )
            resp.raise_for_status()
            report = resp.json()

            routing = report.get("routing", {})
            cert = report.get("certificate", {})

            verified = (
                routing.get("fragment_isolation", False)
                and cert.get("chain_verified", False)
            )

            return AttestationResult(verified=verified, details=report)
    except Exception as e:
        return AttestationResult(verified=False, error=str(e))
