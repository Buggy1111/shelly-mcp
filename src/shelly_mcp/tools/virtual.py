"""Virtual component tools — user-defined components (Gen2+, local-only).

Virtual components (boolean/number/text/enum/button/group) are dynamic components a
script or UI can drive — e.g. a virtual switch a script reacts to. They're listed via
``Shelly.GetComponents`` (dynamic only); add is audited; delete is confirm-gated. Cloud
can't manage them (UnsupportedOnCloud).
"""

from __future__ import annotations

from typing import Any

from shelly_mcp.app import confirm_refusal, execute_and_audit, get_registry, mcp
from shelly_mcp.backends.base import BackendError


@mcp.tool(annotations={"readOnlyHint": True})
async def shelly_virtual_list(device: str) -> dict[str, Any]:
    """List the device's virtual (dynamic) components via ``Shelly.GetComponents``."""
    backend = await get_registry().get_backend(device)
    try:
        result = await backend.call("Shelly.GetComponents", {"dynamic_only": True})
    except BackendError as exc:
        return {"device": device, "components": [], "error": str(exc)}
    components = result.get("components", []) if isinstance(result, dict) else []
    return {"device": device, "components": components}


@mcp.tool(annotations={"idempotentHint": True})
async def shelly_virtual_add(
    device: str, type: str, config: dict[str, Any] | None = None, id: int | None = None
) -> dict[str, Any]:
    """Add a virtual component of ``type`` (boolean/number/text/enum/button/group).

    Optional ``config`` and ``id`` (200-299). Returns the new component id. Audit-logged.
    """
    if not type or not isinstance(type, str):
        return {"error": "type must be a non-empty string (boolean/number/text/enum/button/group)"}
    params: dict[str, Any] = {"type": type}
    if config is not None:
        params["config"] = config
    if id is not None:
        params["id"] = id
    try:
        result = await execute_and_audit(device, "Virtual.Add", params)
    except BackendError as exc:
        return {"device": device, "error": str(exc)}
    return {"device": device, "added": result}


@mcp.tool(annotations={"destructiveHint": True})
async def shelly_virtual_delete(device: str, key: str, confirm: bool = False) -> dict[str, Any]:
    """Delete a virtual component by ``key`` (``<type>:<cid>``). Requires ``confirm:true``."""
    if not key or ":" not in key:
        return {"error": "key must be '<type>:<cid>', e.g. 'boolean:200'"}
    if not confirm:
        return confirm_refusal(device, "Virtual.Delete", {"key": key})
    try:
        result = await execute_and_audit(device, "Virtual.Delete", {"key": key})
    except BackendError as exc:
        return {"device": device, "key": key, "error": str(exc)}
    return {"device": device, "key": key, "deleted": result, "confirmed": True}
