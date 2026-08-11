"""Tests for MCP resources + prompts registration and resource data."""

from __future__ import annotations

import asyncio
from typing import Any

from shelly_mcp.server import mcp
from shelly_mcp.tools.resources import (
    device_status_resource,
    devices_resource,
    shelly_diagnose,
    shelly_energy_report,
    shelly_evening_scene,
)


async def test_devices_resource(wire: Any) -> None:
    out = await devices_resource()
    assert out["count"] == 1
    assert out["devices"][0]["gen"] == 2


async def test_device_status_resource(wire: Any) -> None:
    out = await device_status_resource(name="dev")
    assert "switch:0" in out["channels"]
    assert out["gen"] == 2


def test_prompts_return_workflow_text() -> None:
    assert "warm white" in str(shelly_evening_scene(brightness=20))
    assert "20%" in str(shelly_evening_scene(brightness=20))
    assert "energy" in str(shelly_energy_report()).lower()
    assert "offline" in str(shelly_diagnose()).lower()


def test_resources_and_prompts_registered() -> None:
    resources = asyncio.run(mcp.list_resources())
    templates = asyncio.run(mcp.list_resource_templates())
    prompts = asyncio.run(mcp.list_prompts())
    assert "shelly://devices" in {str(r.uri) for r in resources}
    assert "shelly://device/{name}/status" in {t.uri_template for t in templates}
    assert {"shelly_evening_scene", "shelly_energy_report", "shelly_diagnose"} <= {
        p.name for p in prompts
    }
