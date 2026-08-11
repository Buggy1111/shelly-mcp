"""Tests for energy tools — live readings + best-effort history."""

from __future__ import annotations

from typing import Any

from shelly_mcp.tools.energy import shelly_energy_history, shelly_energy_live


async def test_energy_live_returns_per_channel_fields(wire: Any) -> None:
    out = await shelly_energy_live(device="dev")
    reading = out["readings"]["switch:0"]
    assert reading["power_w"] == 12.0
    assert reading["voltage"] == 230.0
    assert reading["energy_total_wh"] == 1000.0


async def test_energy_live_channel_filter(wire: Any) -> None:
    out = await shelly_energy_live(device="dev", channel=0)
    assert set(out["readings"]) == {"switch:0"}


async def test_energy_history_includes_by_minute_when_present(wire: Any) -> None:
    out = await shelly_energy_history(device="dev")
    ch = out["channels"]["switch:0"]
    assert ch["energy_total_wh"] == 1000.0
    assert ch["recent_by_minute_wh"] == [10, 11, 9]
    assert "switch:0" not in out["degraded"]


async def test_energy_history_marks_degraded_without_series(
    wire: Any, gen2_status: dict[str, Any]
) -> None:
    del gen2_status["switch:0"]["aenergy"]["by_minute"]
    out = await shelly_energy_history(device="dev")
    assert "switch:0" in out["degraded"]
    assert "note" in out
