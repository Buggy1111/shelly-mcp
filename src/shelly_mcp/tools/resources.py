"""MCP resources + prompts — ambient context and one-call workflows.

Resources let a client pin fleet state into context without a tool call; prompts are
pre-built parameterized workflows that make the server feel complete out of the box.
Both attach to the shared ``mcp`` at import time (registered via ``tools`` package).
"""

from __future__ import annotations

from typing import Any

from shelly_mcp.app import get_registry, mcp, resolve_status


@mcp.resource("shelly://devices")
async def devices_resource() -> dict[str, Any]:
    """The current device fleet (identities + online state) as ambient context."""
    devices = await get_registry().list_devices()
    return {"count": len(devices), "devices": [d.model_dump() for d in devices]}


@mcp.resource("shelly://device/{name}/status")
async def device_status_resource(name: str) -> dict[str, Any]:
    """Live normalized status of one device as a resource (no tool call needed)."""
    ident, normalized, _ = await resolve_status(name)
    return {
        "device": ident.id,
        "gen": int(ident.gen),
        "channels": {k: v.model_dump() for k, v in normalized.channels.items()},
        "lights": {k: v.model_dump() for k, v in normalized.lights.items()},
        "covers": {k: v.model_dump() for k, v in normalized.covers.items()},
        "device_temp_c": normalized.device_temp_c,
    }


@mcp.prompt
def shelly_evening_scene(brightness: int = 30) -> str:
    """Workflow: dim configured lights to warm-white and turn plugs off for the evening."""
    return (
        f"Set every light device to warm white at {brightness}% brightness "
        f"(use shelly_light_set with a low temp_k around 2700 and brightness={brightness}), "
        f"then turn off plug/switch devices that aren't powering something essential "
        f"(use shelly_switch_set on=false). List what you changed and ask before turning "
        f"off anything that looks essential (router, fridge)."
    )


@mcp.prompt
def shelly_energy_report() -> str:
    """Workflow: summarize today's power/energy across the fleet."""
    return (
        "List all devices (shelly_list_devices), then for each that reports energy call "
        "shelly_energy_live and summarize: current draw per device, which is using the most "
        "right now, and lifetime total where available. Note any device that can't report "
        "voltage/current (Gen1 limitation) instead of guessing."
    )


@mcp.prompt
def shelly_diagnose() -> str:
    """Workflow: health-check every device (online, firmware, error fields)."""
    return (
        "For every device (shelly_list_devices), check shelly_get_info and shelly_get_status: "
        "report which are offline, which have a firmware update available, and any error or "
        "overpower/overtemperature flags in the raw status. Present it as a short table and "
        "flag anything needing attention."
    )
