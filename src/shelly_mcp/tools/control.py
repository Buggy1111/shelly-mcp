"""Control tools — typed, ergonomic switch / light / cover actions (Gen1↔Gen2 normalized).

These everyday actions are low-stakes and not confirm-gated (the destructive escape
hatches live in ``generic`` and ``system``), but every mutation is **audit-logged**.
Each returns the post-action canonical state so the caller sees the real result, not
just an ack.
"""

from __future__ import annotations

from typing import Any

from shelly_mcp.app import backend_errors, execute_and_audit, mcp, resolve_status
from shelly_mcp.normalize import NormalizedStatus

# Light component key prefix -> the RPC method that drives it (Gen2). Gen1 maps all
# of these through gen1_rest_for() anyway, so the exact choice only matters on Gen2.
_LIGHT_METHOD = {"rgbw": "RGBW.Set", "rgb": "RGB.Set", "cct": "CCT.Set", "light": "Light.Set"}


def _component_for(
    normalized: NormalizedStatus, bucket: str, channel: int
) -> tuple[str, Any] | None:
    """Find the (key, state) in a bucket whose key addresses ``channel`` (``type:channel``)."""
    states: dict[str, Any] = getattr(normalized, bucket)
    for key, state in states.items():
        if key.endswith(f":{channel}"):
            return key, state
    return None


@mcp.tool(annotations={"idempotentHint": True})
@backend_errors
async def shelly_switch_set(
    device: str, on: bool, channel: int = 0, toggle_after_s: int | None = None
) -> dict[str, Any]:
    """Turn a switch/relay channel on or off (optionally auto-revert after N seconds).

    Returns the post-action ``ChannelState``. Audit-logged.
    """
    params: dict[str, Any] = {"id": channel, "on": on}
    if toggle_after_s is not None:
        params["toggle_after"] = toggle_after_s
    await execute_and_audit(device, "Switch.Set", params)
    return await _post_action(device, "channels", channel)


@mcp.tool
@backend_errors
async def shelly_switch_toggle(device: str, channel: int = 0) -> dict[str, Any]:
    """Toggle a switch/relay channel. Returns the post-action ``ChannelState``. Audit-logged."""
    await execute_and_audit(device, "Switch.Toggle", {"id": channel})
    return await _post_action(device, "channels", channel)


@mcp.tool(annotations={"idempotentHint": True})
@backend_errors
async def shelly_light_set(
    device: str,
    channel: int = 0,
    on: bool | None = None,
    brightness: int | None = None,
    rgb: list[int] | None = None,
    white: int | None = None,
    temp_k: int | None = None,
    transition_s: float | None = None,
) -> dict[str, Any]:
    """Set a light/dimmer/RGB(W)/CCT channel (Gen1 /color,/light ↔ Gen2 Light/RGB/RGBW/CCT.Set).

    Only the provided fields are changed. ``brightness`` 0-100, ``rgb`` three 0-255
    values, ``temp_k`` white colour temperature. Returns the post-action ``LightState``.
    Audit-logged.
    """
    if rgb is not None and len(rgb) != 3:
        return {"error": "rgb must be exactly three integers (0-255)"}
    if brightness is not None and not 0 <= brightness <= 100:
        return {"error": "brightness must be between 0 and 100"}

    # Pick the method from the device's actual light component (matters on Gen2).
    _, normalized, _ = await resolve_status(device)
    found = _component_for(normalized, "lights", channel)
    method = "Light.Set"
    if found is not None:
        prefix = found[0].split(":", 1)[0]
        method = _LIGHT_METHOD.get(prefix, "Light.Set")

    params: dict[str, Any] = {"id": channel}
    for name, value in (
        ("on", on), ("brightness", brightness), ("rgb", rgb),
        ("white", white), ("temp_k", temp_k), ("transition", transition_s),
    ):
        if value is not None:
            params[name] = value
    await execute_and_audit(device, method, params)
    return await _post_action(device, "lights", channel)


@mcp.tool
@backend_errors
async def shelly_cover_move(
    device: str, action: str, channel: int = 0, position: int | None = None
) -> dict[str, Any]:
    """Move a roller/cover: ``action`` is open|close|stop, or pass ``position`` (0-100) to go to it.

    Returns the post-action ``CoverState``. Audit-logged.
    """
    if position is not None:
        if not 0 <= position <= 100:
            return {"error": "position must be between 0 and 100"}
        await execute_and_audit(device, "Cover.GoToPosition", {"id": channel, "pos": position})
    else:
        method = {"open": "Cover.Open", "close": "Cover.Close", "stop": "Cover.Stop"}.get(action)
        if method is None:
            return {"error": "action must be one of: open, close, stop (or pass position)"}
        await execute_and_audit(device, method, {"id": channel})
    return await _post_action(device, "covers", channel)


async def _post_action(device: str, bucket: str, channel: int) -> dict[str, Any]:
    """Re-read the device and return the post-action canonical state for one channel."""
    _, normalized, _ = await resolve_status(device)
    found = _component_for(normalized, bucket, channel)
    if found is None:
        return {"device": device, "channel": channel, "state": None}
    key, state = found
    return {"device": device, "component": key, "state": state.model_dump()}
