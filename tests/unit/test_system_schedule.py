"""Tests for system (reboot/update/set_auth) + schedule tools — gates, validation, secrets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from shelly_mcp.tools.schedule import (
    _validate_timespec,
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
    out = await shelly_system_reboot(device="dev")
    assert out["confirmed"] is False
    assert wire.calls == []


async def test_reboot_executes_with_confirm(wire: Any) -> None:
    out = await shelly_system_reboot(device="dev", confirm=True)
    assert out["ok"] is True
    assert any(m == "Shelly.Reboot" for m, _ in wire.calls)


async def test_update_validates_channel(wire: Any) -> None:
    assert "error" in await shelly_system_update(device="dev", channel="nightly", confirm=True)


async def test_set_auth_rejects_short_password(wire: Any) -> None:
    out = await shelly_system_set_auth(device="dev", password="short", confirm=True)
    assert "error" in out
    assert wire.calls == []


async def test_set_auth_preview_does_not_echo_password(wire: Any) -> None:
    out = await shelly_system_set_auth(device="dev", password="averylongpassword")
    assert out["confirmed"] is False
    assert "averylongpassword" not in str(out)


async def test_set_auth_password_redacted_in_audit(wire: Any, tmp_path: Path) -> None:
    await shelly_system_set_auth(device="dev", password="averylongpassword", confirm=True)
    audit_text = (tmp_path / "audit.jsonl").read_text()
    assert "averylongpassword" not in audit_text  # secret never hits the log
    assert "***" in audit_text


# ------------------------------------------------------------------ schedule
async def test_schedule_create_validates_timespec(wire: Any) -> None:
    out = await shelly_schedule_create(
        device="dev", timespec="0 0 22", calls=[{"method": "Switch.Set", "params": {"on": False}}]
    )
    assert "error" in out
    assert "5 (min hour" in out["error"]


@pytest.mark.parametrize(
    "timespec",
    [
        "0 22 * * *",  # 5 fields (seconds default 0)
        "0 0 22 * * MON,TUE,WED,THU",
        "0 0 22 * * * 2027",  # 7 fields (year)
        "@daily",
        "@sunset",
        "@sunrise+30m",
        "@sunset-1h30m",
        "@SUNSET+90",  # bare number = seconds, case-insensitive
        "@sunrise * * MON-FRI",
        "@sunset+15m * 6-8 *",
        "@sunset+12h",
        "@sunset+02h00m",  # the form the device itself reports back
        '@random:{"from":"0 0 18 * * *","to":"0 0 20 * * *","number":2}',
    ],
)
def test_validate_timespec_accepts_device_grammar(timespec: str) -> None:
    assert _validate_timespec(timespec) is None


@pytest.mark.parametrize(
    ("timespec", "fragment"),
    [
        ("", "empty"),
        ("0 0 22", "got 3 fields"),
        ("0 0 22 * * * 2027 x", "got 8 fields"),
        ("@sunset+13h", "max ±12 h"),
        ("@sunset+12h1s", "max ±12 h"),
        ("@sunset * MON", "got 2"),
        ("@sunset+1x", "unknown timespec"),
        ("@noon", "unknown timespec"),
        ("@daily *", "takes no further"),
    ],
)
def test_validate_timespec_rejects_malformed(timespec: str, fragment: str) -> None:
    err = _validate_timespec(timespec)
    assert err is not None and fragment in err


async def test_schedule_create_accepts_sunset(wire: Any) -> None:
    out = await shelly_schedule_create(
        device="dev",
        timespec="@sunset+30m",
        calls=[{"method": "Switch.Set", "params": {"on": True}}],
    )
    assert "error" not in out


async def test_schedule_create_rejects_more_than_five_calls(wire: Any) -> None:
    calls = [{"method": "Switch.Set", "params": {"id": 0, "on": False}}] * 6
    out = await shelly_schedule_create(device="dev", timespec="0 0 22 * * *", calls=calls)
    assert "at most 5 calls" in out["error"]


async def test_schedule_create_rejects_destructive_call(wire: Any) -> None:
    """A schedule must never become a deferred FactoryReset that skips both gates."""
    out = await shelly_schedule_create(
        device="dev", timespec="0 0 3 * * *", calls=[{"method": "Shelly.FactoryReset"}]
    )
    assert "not allowed in a schedule" in out["error"]
    assert wire.calls == []


async def test_schedule_create_rejects_gate_bypassing_writes(wire: Any) -> None:
    """Script.Eval / SetAuth / Webhook.Create are WRITE but gated — no smuggling via schedule."""
    for method in ("Script.Eval", "Script.PutCode", "Shelly.SetAuth", "Webhook.Create"):
        out = await shelly_schedule_create(
            device="dev", timespec="0 0 22 * * *", calls=[{"method": method}]
        )
        assert "not allowed in a schedule" in out["error"], method
    assert wire.calls == []


async def test_schedule_update_rejects_gate_bypassing_calls(wire: Any) -> None:
    out = await shelly_schedule_update(
        device="dev", id=1, calls=[{"method": "Shelly.FactoryReset"}]
    )
    assert "not allowed in a schedule" in out["error"]
    assert wire.calls == []


async def test_schedule_create_rejects_read_call(wire: Any) -> None:
    out = await shelly_schedule_create(
        device="dev", timespec="0 0 22 * * *", calls=[{"method": "Shelly.GetStatus"}]
    )
    assert "error" in out


async def test_schedule_create_ok(wire: Any) -> None:
    out = await shelly_schedule_create(
        device="dev",
        timespec="0 0 22 * * *",
        calls=[{"method": "Switch.Set", "params": {"id": 0, "on": False}}],
    )
    assert "created" in out
    assert any(m == "Schedule.Create" for m, _ in wire.calls)


async def test_schedule_create_enforces_max(wire: Any, gen2_status: dict[str, Any]) -> None:
    gen2_status["_schedules"] = [{"id": i} for i in range(20)]  # already at the cap
    out = await shelly_schedule_create(
        device="dev",
        timespec="0 0 22 * * *",
        calls=[{"method": "Switch.Set", "params": {"on": False}}],
    )
    assert "error" in out
    assert "max" in out["error"]


async def test_schedule_delete_confirm_gate(wire: Any) -> None:
    refused = await shelly_schedule_delete(device="dev", id=1)
    assert refused["confirmed"] is False
    ok = await shelly_schedule_delete(device="dev", id=1, confirm=True)
    assert ok["confirmed"] is True
    assert any(m == "Schedule.Delete" for m, _ in wire.calls)


async def test_schedule_list(wire: Any, gen2_status: dict[str, Any]) -> None:
    gen2_status["_schedules"] = [{"id": 1, "enable": True}]
    out = await shelly_schedule_list(device="dev")
    assert out["schedules"] == [{"id": 1, "enable": True}]
