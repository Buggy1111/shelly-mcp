"""Unit tests for the audit log — append-only JSONL with secret redaction (A09/A02)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shelly_mcp.audit import AuditLog, redact


def _lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_record_appends_one_jsonl_line(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    log.record(device="televize", method="Switch.Set", params={"id": 0, "on": False}, ok=True)
    log.record(device="led", method="Light.Set", params={"brightness": 40}, ok=True)
    entries = _lines(log.path)
    assert len(entries) == 2
    assert entries[0]["device"] == "televize"
    assert entries[0]["method"] == "Switch.Set"
    assert entries[0]["ok"] is True
    assert "ts" in entries[0]


def test_secrets_are_redacted_in_params(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    log.record(device="x", method="Sys.SetConfig", params={"password": "hunter2", "id": 0}, ok=True)
    entry = _lines(log.path)[0]
    assert entry["params"]["password"] == "***"
    assert entry["params"]["id"] == 0
    assert "hunter2" not in log.path.read_text()


def test_nested_secret_redaction() -> None:
    out = redact({"config": {"auth_key": "abc", "name": "kitchen"}, "token": "t"})
    assert out["config"]["auth_key"] == "***"
    assert out["config"]["name"] == "kitchen"
    assert out["token"] == "***"


def test_long_values_truncated() -> None:
    out = redact({"code": "x" * 500})
    assert out["code"].endswith("…")
    assert len(out["code"]) <= 202


def test_error_recorded_without_result(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    log.record(device="x", method="Switch.Set", params={}, ok=False, error="device unreachable")
    entry = _lines(log.path)[0]
    assert entry["ok"] is False
    assert entry["error"] == "device unreachable"
    assert "result" not in entry


def test_audit_write_failure_is_swallowed(tmp_path: Path) -> None:
    # A bad path must not raise — losing a log line beats crashing the device op.
    bad = tmp_path / "a_file"
    bad.write_text("i am a file, not a dir")
    log = AuditLog(bad / "audit.jsonl")  # parent is a file -> mkdir/open will fail
    log.record(device="x", method="Switch.Set", params={}, ok=True)  # must not raise
