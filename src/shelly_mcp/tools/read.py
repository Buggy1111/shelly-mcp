"""Read tools — safe, read-only inspection of devices (the starting point)."""

from __future__ import annotations

from typing import Any

from shelly_mcp import __version__, discovery
from shelly_mcp.app import backend_errors, get_registry, mcp, resolve_status
from shelly_mcp.audit import redact_config
from shelly_mcp.backends.base import BackendError


@mcp.tool
def shelly_version() -> dict[str, str]:
    """Return the shelly-mcp server version (health check)."""
    return {"name": "shelly-mcp", "version": __version__}


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
async def shelly_discover(timeout_s: float = 5.0, use_cloud: bool = True) -> dict[str, Any]:
    """Discover Shelly devices on the LAN via mDNS, merged with the cloud account list.

    ``timeout_s`` is the mDNS browse window. Set ``use_cloud=false`` to skip the cloud
    list (LAN-only). Safe, read-only; returns lightweight identities (probe for detail).
    """
    mdns = await discovery.discover_mdns(timeout_s)
    cloud = []
    if use_cloud:
        try:
            cloud = await get_registry().list_devices()
        except BackendError:
            cloud = []
    merged = discovery.merge_discovered(mdns, cloud)
    return {"count": len(merged), "devices": [d.model_dump() for d in merged]}


@mcp.tool(annotations={"readOnlyHint": True})
async def shelly_list_devices() -> dict[str, Any]:
    """List every Shelly device known to this server (configured + cloud account).

    Safe, read-only. Returns each device's canonical identity (id, name, generation,
    model, online state) — the starting point before any status or control call.
    """
    devices = await get_registry().list_devices()
    return {"count": len(devices), "devices": [d.model_dump() for d in devices]}


@mcp.tool(annotations={"readOnlyHint": True})
async def shelly_get_info(device: str) -> dict[str, Any]:
    """Identify one device (generation, model, firmware, online state, capabilities).

    ``device`` is a device id or a configured name. Safe, read-only.
    """
    registry = get_registry()
    ident = await registry.require_identity(device)
    caps = registry.capabilities(device)
    return {
        "identity": ident.model_dump(),
        "capabilities": caps.model_dump() if caps is not None else None,
    }


@mcp.tool(annotations={"readOnlyHint": True})
async def shelly_get_status(device: str, component: str | None = None) -> dict[str, Any]:
    """Get a device's **normalized** live status (Gen1/Gen2/Cloud folded into one shape).

    Returns canonical channels/lights/covers plus the raw per-generation payload. Pass
    ``component`` (e.g. ``"switch:0"``) to narrow to a single component. Safe, read-only.
    """
    ident, normalized, raw = await resolve_status(device)
    result: dict[str, Any] = {
        "device": ident.id,
        "gen": int(ident.gen),
        "channels": {k: v.model_dump() for k, v in normalized.channels.items()},
        "lights": {k: v.model_dump() for k, v in normalized.lights.items()},
        "covers": {k: v.model_dump() for k, v in normalized.covers.items()},
        "device_temp_c": normalized.device_temp_c,
    }
    if component is not None:
        result["channels"] = {k: v for k, v in result["channels"].items() if k == component}
        result["lights"] = {k: v for k, v in result["lights"].items() if k == component}
        result["covers"] = {k: v for k, v in result["covers"].items() if k == component}
        result["raw"] = raw.get(component, {}) if isinstance(raw, dict) else {}
    else:
        result["raw"] = raw
    return result


@mcp.tool(annotations={"readOnlyHint": True})
@backend_errors
async def shelly_list_components(device: str) -> dict[str, Any]:
    """List the component keys present on a device (e.g. ['switch:0', 'input:0']).

    Safe, read-only. Use this to discover what a specific device exposes before
    reading status or controlling it.
    """
    backend = await get_registry().get_backend(device)
    components = await backend.list_components()
    return {"device": device, "components": components}


@mcp.tool(annotations={"readOnlyHint": True})
@backend_errors
async def shelly_get_config(device: str, component: str | None = None) -> dict[str, Any]:
    """Get a device's configuration, with credential fields masked as ``***`` (Gen1
    ``/settings`` returns Wi-Fi/MQTT secrets in the clear — they must not reach the
    model). Local-first — the Shelly Cloud API can't expose config, so this returns
    an actionable error for cloud-only devices.
    """
    backend = await get_registry().get_backend(device)
    config = await backend.get_config()
    if component is not None and isinstance(config, dict):
        config = {k: v for k, v in config.items() if k == component}
    return {"device": device, "config": redact_config(config)}
