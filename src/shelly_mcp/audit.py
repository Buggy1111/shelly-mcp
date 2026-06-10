"""Audit log: append-only JSONL, one line per mutation, secrets redacted (A09).

Every mutating tool call writes one record so the user can answer "what changed and
when". Secrets (passwords, auth keys) are redacted before they ever touch the file —
the audit log must never become a place where credentials leak (A09 + A02).

Writes are best-effort: an audit failure must not block or crash a device operation
(losing one log line is better than failing the user's action), but it is reported.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("shelly_mcp.audit")

# Param keys whose values are secrets and must never be written to the log. (Bare "key"
# is deliberately NOT here: KVS.Set/Delete use {"key": slot_name} where the name is not a
# secret; real secrets are covered by password/pass/auth_key/secret/token.)
_SECRET_KEYS = frozenset({"password", "pass", "auth_key", "secret", "token"})
_REDACTED = "***"
_MAX_VALUE_LEN = 200  # keep summaries small; truncate long blobs (e.g. script code)
# Strip embedded credentials from URLs (e.g. a webhook url https://user:pass@host).
_URL_CREDS = re.compile(r"(://)[^/@\s:]+:[^/@\s]+@")


def _redact_value(value: Any) -> Any:
    """Recursively redact a value: mask URL creds in strings, recurse dicts AND lists."""
    if isinstance(value, str):
        value = _URL_CREDS.sub(r"\1***@", value)
        return value[:_MAX_VALUE_LEN] + "…" if len(value) > _MAX_VALUE_LEN else value
    if isinstance(value, dict):
        return redact(value)
    if isinstance(value, list):
        return [_redact_value(v) for v in value]
    return value


def default_audit_path() -> Path:
    """``$SHELLY_MCP_AUDIT`` or the XDG state default (``~/.local/state/shelly-mcp``)."""
    env = os.environ.get("SHELLY_MCP_AUDIT")
    if env:
        return Path(env).expanduser()
    base = os.environ.get("XDG_STATE_HOME", "~/.local/state")
    return Path(base).expanduser() / "shelly-mcp" / "audit.jsonl"


def redact(params: dict[str, Any] | None) -> dict[str, Any]:
    """Return a copy of ``params`` with secret values masked and long values truncated.

    Recurses into nested dicts AND lists (so a secret-keyed param or a credential-bearing
    URL inside a ``calls``/``urls`` list is masked too).
    """
    if not params:
        return {}
    return {
        key: _REDACTED if key.lower() in _SECRET_KEYS else _redact_value(value)
        for key, value in params.items()
    }


# Device CONFIG payloads carry their own secrets under keys the generic set doesn't
# cover — Gen1 /settings exposes the Wi-Fi PSK as "key" and MQTT password as "pass".
# Bare "key" stays out of _SECRET_KEYS (KVS uses it for slot names); config redaction
# adds it, plus suffix matching for *_key / *_pass / *_secret / *_token style fields.
_CONFIG_SECRET_KEYS = _SECRET_KEYS | frozenset({"key"})
_CONFIG_SECRET_SUFFIXES = ("_key", "_pass", "_password", "_secret", "_token")


def redact_config(value: Any) -> Any:
    """Recursively mask secret-bearing fields in a device config payload.

    Used by ``shelly_get_config`` before the config reaches the model: Gen2 devices
    mostly mask their own secrets, but Gen1 ``/settings`` returns Wi-Fi/MQTT/login
    credentials in the clear. Unlike :func:`redact` this never truncates — config
    values are data the caller acts on, not log summaries.
    """
    if isinstance(value, dict):
        return {
            k: _REDACTED
            if k.lower() in _CONFIG_SECRET_KEYS or k.lower().endswith(_CONFIG_SECRET_SUFFIXES)
            else redact_config(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact_config(v) for v in value]
    if isinstance(value, str):
        return _URL_CREDS.sub(r"\1***@", value)
    return value


class AuditLog:
    """Append-only JSONL audit sink. One instance per server process."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or default_audit_path()

    @property
    def path(self) -> Path:
        return self._path

    def record(
        self,
        *,
        device: str,
        method: str,
        params: dict[str, Any] | None = None,
        ok: bool,
        result: Any = None,
        error: str | None = None,
    ) -> None:
        """Append one audit record. Best-effort: logs and swallows write failures."""
        entry = {
            "ts": time.time(),
            "device": device,
            "method": method,
            "params": redact(params),
            "ok": ok,
        }
        if error is not None:
            entry["error"] = error[:_MAX_VALUE_LEN]
        elif result is not None:
            entry["result"] = _summarize(result)
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except OSError as exc:  # never let an audit failure break the device op
            logger.warning("audit write failed (%s): %s", self._path, exc)


def _summarize(result: Any) -> Any:
    """Keep a small, JSON-safe summary of a result (dicts truncated to their keys)."""
    if isinstance(result, dict):
        redacted = redact(result)
        return redacted if len(redacted) <= 8 else {"keys": sorted(redacted)[:8]}
    if isinstance(result, str):
        return result[:_MAX_VALUE_LEN]
    return result
