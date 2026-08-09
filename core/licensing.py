"""Offline Pro license activation (HMAC-signed keys)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import sys
import time
from typing import Optional

from core.config_store import load_config, save_config

# Dev-only fallback when not frozen and no env/baked secret is present.
# Never used in release/frozen builds (fail closed — keys will not validate).
_DEFAULT_SECRET = b"VSS-CHANGE-ME-IN-RELEASE-BUILDS-2026"
LICENSE_PREFIX = "VSS1"


def _bundled_secret() -> str:
    try:
        from core.license_secrets import BUNDLED_LICENSE_SECRET  # type: ignore

        return (BUNDLED_LICENSE_SECRET or "").strip()
    except Exception:
        return ""


def _secret() -> bytes:
    import os

    raw = os.environ.get("VSS_LICENSE_SECRET", "").strip()
    if raw:
        return raw.encode("utf-8")

    bundled = _bundled_secret()
    if bundled:
        return bundled.encode("utf-8")

    # Shipped binaries must not accept keys signed with the public default.
    if getattr(sys, "frozen", False):
        return b""

    return _DEFAULT_SECRET


def _sign_payload(payload: dict) -> str:
    secret = _secret()
    if not secret:
        return ""
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(secret, body, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")


def generate_license_key(email: str = "", tier: str = "pro", years: int = 99) -> str:
    """Generate a signed license key (for beta / manual sales)."""
    if not _secret():
        raise RuntimeError(
            "Set VSS_LICENSE_SECRET (or bake core/license_secrets.py) before generating keys."
        )
    payload = {
        "tier": tier,
        "email": email.strip().lower(),
        "exp": int(time.time()) + years * 365 * 86400,
    }
    sig = _sign_payload(payload)
    blob = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii").rstrip("=")
    return f"{LICENSE_PREFIX}-{blob}.{sig}"


def _parse_key(key: str) -> Optional[dict]:
    key = key.strip()
    if not key.startswith(f"{LICENSE_PREFIX}-"):
        return None
    rest = key[len(LICENSE_PREFIX) + 1 :]
    if "." not in rest:
        return None
    blob, sig = rest.rsplit(".", 1)
    try:
        pad = "=" * (-len(blob) % 4)
        payload = json.loads(base64.urlsafe_b64decode(blob + pad).decode("utf-8"))
    except Exception:
        return None
    expected = _sign_payload(payload)
    if not expected or not hmac.compare_digest(expected, sig):
        return None
    if payload.get("exp", 0) < time.time():
        return None
    return payload


def _license_from_config() -> Optional[dict]:
    cfg = load_config()
    lic = cfg.get("license")
    if isinstance(lic, dict) and lic.get("valid"):
        if lic.get("exp", 0) >= time.time():
            return lic
    return None


def _dev_pro_unlocked() -> bool:
    """True when SPINDLE_DEV_PRO / VSS_DEV_PRO is set (local testing only)."""
    import os

    raw = (
        os.environ.get("SPINDLE_DEV_PRO", "").strip()
        or os.environ.get("VSS_DEV_PRO", "").strip()
    ).lower()
    return raw in {"1", "true", "yes", "on"}


def is_pro() -> bool:
    if _dev_pro_unlocked():
        return True
    return _license_from_config() is not None


def license_summary() -> str:
    if _dev_pro_unlocked() and _license_from_config() is None:
        return "Pro (dev)"
    lic = _license_from_config()
    if not lic:
        return "Free"
    email = lic.get("email") or "Licensed"
    return f"Pro ({email})"


def activate_license(key: str) -> tuple[bool, str]:
    payload = _parse_key(key)
    if not payload:
        return False, "Invalid or expired license key."
    cfg = load_config()
    cfg["license"] = {
        "valid": True,
        "tier": payload.get("tier", "pro"),
        "email": payload.get("email", ""),
        "exp": payload.get("exp", 0),
        "key_hint": re.sub(r"(.{4}).*(.{4})", r"\1…\2", key.strip())[:24],
    }
    save_config(cfg)
    return True, "Pro activated. Thank you!"


def deactivate_license() -> None:
    cfg = load_config()
    cfg.pop("license", None)
    save_config(cfg)
