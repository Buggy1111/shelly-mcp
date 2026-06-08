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
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("shelly_mcp.audit")

# Param keys whose values are secrets and must never be written to the log.
_SECRET_KEYS = frozenset({"password", "pass", "auth_key", "key", "secret", "token"})
_REDACTED = "***"
_MAX_VALUE_LEN = 200  # keep summaries small; truncate long blobs (e.g. script code)


def default_audit_path() -> Path:
    """``$SHELLY_MCP_AUDIT`` or the XDG state default (``~/.local/state/shelly-mcp``)."""
    env = os.environ.get("SHELLY_MCP_AUDIT")
    if env:
        return Path(env).expanduser()
    base = os.environ.get("XDG_STATE_HOME", "~/.local/state")
    return Path(base).expanduser() / "shelly-mcp" / "audit.jsonl"


def redact(params: dict[str, Any] | None) -> dict[str, Any]:
    """Return a copy of ``params`` with secret values masked and long values truncated."""
    if not params:
        return {}
    out: dict[str, Any] = {}
    for key, value in params.items():
        if key.lower() in _SECRET_KEYS:
            out[key] = _REDACTED
        elif isinstance(value, str) and len(value) > _MAX_VALUE_LEN:
            out[key] = value[:_MAX_VALUE_LEN] + "…"
        elif isinstance(value, dict):
            out[key] = redact(value)
        else:
            out[key] = value
    return out


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
