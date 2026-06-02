"""Validação de assinatura dos webhooks enviados pelo Ghost."""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class GhostSignatureVerification:
    valid: bool
    reason: Optional[str] = None


def _parse_signature_header(value: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for raw_part in value.split(","):
        key, separator, raw_value = raw_part.strip().partition("=")
        if separator:
            parts[key] = raw_value
    return parts


def verify_ghost_signature(
    raw_body: bytes,
    signature_header: Optional[str],
    secret: str,
    *,
    now_ms: Optional[int] = None,
    tolerance_seconds: int = 300,
) -> GhostSignatureVerification:
    """Confere `X-Ghost-Signature` sem expor o segredo em logs."""

    if not signature_header:
        return GhostSignatureVerification(False, "missing_signature")
    if not secret:
        return GhostSignatureVerification(False, "missing_secret")

    parts = _parse_signature_header(signature_header)
    received_hash = parts.get("sha256")
    timestamp = parts.get("t")
    if not received_hash or not timestamp:
        return GhostSignatureVerification(False, "malformed_signature")

    try:
        timestamp_ms = int(timestamp)
    except ValueError:
        return GhostSignatureVerification(False, "invalid_timestamp")

    current_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    tolerance_ms = tolerance_seconds * 1000
    if tolerance_seconds > 0 and abs(current_ms - timestamp_ms) > tolerance_ms:
        return GhostSignatureVerification(False, "stale_signature")

    expected = hmac.new(
        secret.encode("utf-8"),
        raw_body + timestamp.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, received_hash):
        return GhostSignatureVerification(False, "invalid_signature")

    return GhostSignatureVerification(True)


__all__ = ["GhostSignatureVerification", "verify_ghost_signature"]

