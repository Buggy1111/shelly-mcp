"""KVS tools — the device's key-value store (Gen2+, local-only).

A small persistent JSON store on the device, handy for scripts and automation state.
Cloud can't reach it (the backend raises UnsupportedOnCloud). Reads are safe; set is
audited; delete is confirm-gated.
"""

from __future__ import annotations

from typing import Any

from shelly_mcp.app import confirm_refusal, execute_and_audit, get_registry, mcp
from shelly_mcp.backends.base import BackendError


@mcp.tool(annotations={"readOnlyHint": True})
async def shelly_kvs_list(device: str, match: str = "*") -> dict[str, Any]:
    """List KVS keys (with their etags). ``match`` is a wildcard pattern (default all)."""
    backend = await get_registry().get_backend(device)
    try:
        result = await backend.call("KVS.List", {"match": match})
    except BackendError as exc:
        return {"device": device, "keys": {}, "error": str(exc)}
    result = result if isinstance(result, dict) else {}
    return {"device": device, "keys": result.get("keys", {}), "rev": result.get("rev")}


@mcp.tool(annotations={"readOnlyHint": True})
async def shelly_kvs_get(device: str, key: str) -> dict[str, Any]:
    """Get one KVS value (with its etag) by key."""
    backend = await get_registry().get_backend(device)
    try:
        result = await backend.call("KVS.Get", {"key": key})
    except BackendError as exc:
        return {"device": device, "key": key, "error": str(exc)}
    payload = result if isinstance(result, dict) else {"value": result}
    return {"device": device, "key": key, **payload}


@mcp.tool(annotations={"idempotentHint": True})
async def shelly_kvs_set(device: str, key: str, value: Any) -> dict[str, Any]:
    """Set a KVS key to a JSON value. Audit-logged."""
    if not key or not isinstance(key, str):
        return {"error": "key must be a non-empty string"}
    try:
        result = await execute_and_audit(device, "KVS.Set", {"key": key, "value": value})
    except BackendError as exc:
        return {"device": device, "key": key, "error": str(exc)}
    return {"device": device, "key": key, "set": result}


@mcp.tool(annotations={"destructiveHint": True})
async def shelly_kvs_delete(device: str, key: str, confirm: bool = False) -> dict[str, Any]:
    """Delete a KVS key. Requires ``confirm:true``. Audit-logged."""
    if not confirm:
        return confirm_refusal(device, "KVS.Delete", {"key": key})
    try:
        result = await execute_and_audit(device, "KVS.Delete", {"key": key})
    except BackendError as exc:
        return {"device": device, "key": key, "error": str(exc)}
    return {"device": device, "key": key, "deleted": result, "confirmed": True}
