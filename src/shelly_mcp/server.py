"""FastMCP application entry point + tool registry.

M1 ships the read tools (`shelly_list_devices`, `shelly_get_info`,
`shelly_get_status`, `shelly_list_components`); control/automation tools land in
later milestones. Tools are thin: they validate input, delegate to the
:class:`DeviceRegistry`, normalize via :class:`Normalizer`, and return
``structuredContent`` (a plain dict) plus a human summary.

Read tools are safe (``readOnlyHint``); mutating tools (M2+) will gate on
``confirm:true`` (LLM06 — no destructive action without explicit human approval).
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from shelly_mcp import __version__
from shelly_mcp.backends.base import BackendError
from shelly_mcp.client import DeviceRegistry
from shelly_mcp.config import load_config
from shelly_mcp.normalize import Normalizer

mcp: FastMCP = FastMCP(
    name="shelly-mcp",
    instructions=(
        "Control and automate Shelly smart-home devices (Gen1-Gen4 + BLU), local-first. "
        "Read tools are safe; mutating tools require confirm:true. "
        "Unofficial community project, not affiliated with Allterco/Shelly."
    ),
)

# Module-global registry, built lazily from config on first use. Tests inject a
# fake via set_registry() so no tool ever needs a live network.
_registry: DeviceRegistry | None = None


def get_registry() -> DeviceRegistry:
    """Return the process-wide device registry, building it from config if needed."""
    global _registry
    if _registry is None:
        _registry = DeviceRegistry(load_config())
    return _registry


def set_registry(registry: DeviceRegistry | None) -> None:
    """Override (or clear) the global registry — used for explicit wiring and tests."""
    global _registry
    _registry = registry


@mcp.tool
def shelly_version() -> dict[str, str]:
    """Return the shelly-mcp server version (health check)."""
    return {"name": "shelly-mcp", "version": __version__}


@mcp.tool(annotations={"readOnlyHint": True})
async def shelly_list_devices() -> dict[str, Any]:
    """List every Shelly device known to this server (configured + cloud account).

    Safe, read-only. Returns each device's canonical identity (id, name, generation,
    model, online state) — the starting point before any status or control call.
    """
    devices = await get_registry().list_devices()
    return {
        "count": len(devices),
        "devices": [d.model_dump() for d in devices],
    }


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
    registry = get_registry()
    ident = await registry.require_identity(device)
    backend = await registry.get_backend(device)
    raw = await backend.get_status()
    normalized = Normalizer.normalize_status(raw, ident.gen, backend=ident.backend or "local_rest")

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
async def shelly_list_components(device: str) -> dict[str, Any]:
    """List the component keys present on a device (e.g. ['switch:0', 'input:0']).

    Safe, read-only. Use this to discover what a specific device exposes before
    reading status or controlling it.
    """
    backend = await get_registry().get_backend(device)
    try:
        components = await backend.list_components()
    except BackendError as exc:
        return {"device": device, "error": str(exc), "components": []}
    return {"device": device, "components": components}


def main() -> None:
    """Console entry point: run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
