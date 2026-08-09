"""Persist GUI settings and manual order paths."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from core.paths import migrate_user_file

CONFIG_FILE = migrate_user_file("config.json", legacy_names=(".discogs_config.json",))
MANUAL_ORDER_FILE = migrate_user_file(
  "manual_order.json",
  legacy_names=(".discogs_manual_order.json",),
)

_OBFUSCATE_KEY = b"DiscogsVinylSorter2026"


def _obfuscate(text: str) -> str:
  if not text:
    return ""
  data = text.encode("utf-8")
  key = _OBFUSCATE_KEY
  result = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
  return base64.b64encode(result).decode("ascii")


def _deobfuscate(encoded: str) -> str:
  if not encoded:
    return ""
  try:
    data = base64.b64decode(encoded.encode("ascii"))
    key = _OBFUSCATE_KEY
    result = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return result.decode("utf-8")
  except Exception:
    return ""


def load_config() -> dict:
  """Load saved configuration from file."""
  try:
    if CONFIG_FILE.exists():
      with CONFIG_FILE.open("r", encoding="utf-8") as f:
        config = json.load(f)
        if "token_encrypted" in config:
          config["token"] = _deobfuscate(config.pop("token_encrypted"))
        if "oauth_access_token_encrypted" in config:
          config["oauth_access_token"] = _deobfuscate(config.pop("oauth_access_token_encrypted"))
        if "oauth_access_secret_encrypted" in config:
          config["oauth_access_secret"] = _deobfuscate(config.pop("oauth_access_secret_encrypted"))
        return config
  except Exception:
    pass
  return {}


def save_config(config: dict) -> None:
  """Save configuration to file."""
  try:
    save_data = config.copy()
    if "token" in save_data:
      save_data["token_encrypted"] = _obfuscate(save_data.pop("token"))
    if "oauth_access_token" in save_data:
      save_data["oauth_access_token_encrypted"] = _obfuscate(save_data.pop("oauth_access_token"))
    if "oauth_access_secret" in save_data:
      save_data["oauth_access_secret_encrypted"] = _obfuscate(save_data.pop("oauth_access_secret"))
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
      json.dump(save_data, f, indent=2)
  except Exception:
    pass
