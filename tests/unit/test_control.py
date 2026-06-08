"""Tests for control tools — switch/light/cover: call mapping, validation, audit, state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shelly_mcp.tools.control import (
    shelly_cover_move,
    shelly_light_set,
    shelly_switch_set,
    shelly_switch_toggle,
)


async def test_switch_set_off_calls_and_returns_state(wire: Any) -> None:
    out = await shelly_switch_set.fn(device="dev", on=False, channel=0)
    assert ("Switch.Set", {"id": 0, "on": False}) in wire.calls
    assert out["component"] == "switch:0"
    assert out["state"]["output"] is False  # post-action state reflects the change


async def test_switch_toggle(wire: Any) -> None:
    out = await shelly_switch_toggle.fn(device="dev", channel=0)
    assert ("Switch.Toggle", {"id": 0}) in wire.calls
    assert out["state"]["output"] is False  # was True in fixture, toggled


async def test_switch_set_toggle_after(wire: Any) -> None:
    await shelly_switch_set.fn(device="dev", on=True, toggle_after_s=30)
    method, params = wire.calls[-1]
    assert method == "Switch.Set"
    assert params["toggle_after"] == 30


async def test_light_set_picks_rgbw_method_from_component(wire: Any) -> None:
    # The device's light component is rgbw:0, so the tool must emit RGBW.Set (not Light.Set).
    await shelly_light_set.fn(device="dev", rgb=[1, 2, 3], brightness=40)
    methods = [m for m, _ in wire.calls]
    assert "RGBW.Set" in methods


async def test_light_set_validates_rgb_and_brightness(wire: Any) -> None:
    assert "error" in await shelly_light_set.fn(device="dev", rgb=[1, 2])
    assert "error" in await shelly_light_set.fn(device="dev", brightness=150)


async def test_cover_move_open(wire: Any) -> None:
    await shelly_cover_move.fn(device="dev", action="open")
    assert ("Cover.Open", {"id": 0}) in wire.calls


async def test_cover_move_to_position(wire: Any) -> None:
    await shelly_cover_move.fn(device="dev", action="", position=70)
    assert ("Cover.GoToPosition", {"id": 0, "pos": 70}) in wire.calls


async def test_cover_move_invalid_action(wire: Any) -> None:
    assert "error" in await shelly_cover_move.fn(device="dev", action="sideways")
    assert "error" in await shelly_cover_move.fn(device="dev", action="open", position=200)


async def test_mutations_are_audit_logged(wire: Any, tmp_path: Path) -> None:
    await shelly_switch_set.fn(device="dev", on=False)
    lines = [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text().splitlines()]
    assert any(e["method"] == "Switch.Set" and e["ok"] for e in lines)
