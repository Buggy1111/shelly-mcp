"""Tests for system (reboot/update/set_auth) + schedule tools — gates, validation, secrets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from shelly_mcp.tools.schedule import (
    shelly_schedule_create,
    shelly_schedule_delete,
    shelly_schedule_list,
    shelly_schedule_update,
)
from shelly_mcp.tools.system import (
    shelly_system_reboot,
    shelly_system_set_auth,
    shelly_system_update,
)


# ------------------------------------------------------------------- system
async def test_reboot_refuses_without_confirm(wire: Any) -> None:
    out = await shelly_system_reboot.fn(device="dev")
    assert out["confirmed"] is False
    assert wire.calls == []


async def test_reboot_executes_with_confirm(wire: Any) -> None:
    out = await shelly_system_reboot.fn(device="dev", confirm=True)
    assert out["ok"] is True
    assert any(m == "Shelly.Reboot" for m, _ in wire.calls)


async def test_update_validates_channel(wire: Any) -> None:
    assert "error" in await shelly_system_update.fn(device="dev", channel="nightly", confirm=True)


async def test_set_auth_rejects_short_password(wire: Any) -> None:
    out = await shelly_system_set_auth.fn(device="dev", password="short", confirm=True)
    assert "error" in out
    assert wire.calls == []


async def test_set_auth_preview_does_not_echo_password(wire: Any) -> None:
    out = await shelly_system_set_auth.fn(device="dev", password="averylongpassword")
    assert out["confirmed"] is False
    assert "averylongpassword" not in str(out)


async def test_set_auth_password_redacted_in_audit(wire: Any, tmp_path: Path) -> None:
    await shelly_system_set_auth.fn(device="dev", password="averylongpassword", confirm=True)
    audit_text = (tmp_path / "audit.jsonl").read_text()
    assert "averylongpassword" not in audit_text  # secret never hits the log
    assert "***" in audit_text


# ------------------------------------------------------------------ schedule
async def test_schedule_create_validates_timespec(wire: Any) -> None:
    out = await shelly_schedule_create.fn(
        device="dev", timespec="0 0 22", calls=[{"method": "Switch.Set", "params": {"on": False}}]
    )
    assert "error" in out
    assert "6-field" in out["error"]


async def test_schedule_create_rejects_destructive_call(wire: Any) -> None:
    """A schedule must never become a deferred FactoryReset that skips both gates."""
    out = await shelly_schedule_create.fn(
        device="dev", timespec="0 0 3 * * *", calls=[{"method": "Shelly.FactoryReset"}]
    )
    assert "not allowed in a schedule" in out["error"]
    assert wire.calls == []


async def test_schedule_create_rejects_gate_bypassing_writes(wire: Any) -> None:
    """Script.Eval / SetAuth / Webhook.Create are WRITE but gated — no smuggling via schedule."""
    for method in ("Script.Eval", "Script.PutCode", "Shelly.SetAuth", "Webhook.Create"):
        out = await shelly_schedule_create.fn(
            device="dev", timespec="0 0 22 * * *", calls=[{"method": method}]
        )
        assert "not allowed in a schedule" in out["error"], method
    assert wire.calls == []


async def test_schedule_update_rejects_gate_bypassing_calls(wire: Any) -> None:
    out = await shelly_schedule_update.fn(
        device="dev", id=1, calls=[{"method": "Shelly.FactoryReset"}]
    )
    assert "not allowed in a schedule" in out["error"]
    assert wire.calls == []


async def test_schedule_create_rejects_read_call(wire: Any) -> None:
    out = await shelly_schedule_create.fn(
        device="dev", timespec="0 0 22 * * *", calls=[{"method": "Shelly.GetStatus"}]
    )
    assert "error" in out


async def test_schedule_create_ok(wire: Any) -> None:
    out = await shelly_schedule_create.fn(
        device="dev",
        timespec="0 0 22 * * *",
        calls=[{"method": "Switch.Set", "params": {"id": 0, "on": False}}],
    )
    assert "created" in out
    assert any(m == "Schedule.Create" for m, _ in wire.calls)


async def test_schedule_create_enforces_max(wire: Any, gen2_status: dict[str, Any]) -> None:
    gen2_status["_schedules"] = [{"id": i} for i in range(20)]  # already at the cap
    out = await shelly_schedule_create.fn(
        device="dev", timespec="0 0 22 * * *",
        calls=[{"method": "Switch.Set", "params": {"on": False}}],
    )
    assert "error" in out
    assert "max" in out["error"]


async def test_schedule_delete_confirm_gate(wire: Any) -> None:
    refused = await shelly_schedule_delete.fn(device="dev", id=1)
    assert refused["confirmed"] is False
    ok = await shelly_schedule_delete.fn(device="dev", id=1, confirm=True)
    assert ok["confirmed"] is True
    assert any(m == "Schedule.Delete" for m, _ in wire.calls)


async def test_schedule_list(wire: Any, gen2_status: dict[str, Any]) -> None:
    gen2_status["_schedules"] = [{"id": 1, "enable": True}]
    out = await shelly_schedule_list.fn(device="dev")
    assert out["schedules"] == [{"id": 1, "enable": True}]
