"""Generic engine — the escape hatch that makes the server cover 100% of the API.

``shelly_rpc`` runs any **read** method; ``shelly_rpc_write`` runs any mutating method
behind the confirm gate (+ a data-loss double-gate for destructive ones). Together
they reach every component — present and future — without 150 hand-written tools
(ADR-002), while the classification in :mod:`shelly_mcp.methods` keeps reads safe and
writes gated (docs/03-SECURITY §5).
"""

from __future__ import annotations

from typing import Any

from shelly_mcp.app import confirm_refusal, execute_and_audit, get_registry, mcp
from shelly_mcp.backends.base import BackendError
from shelly_mcp.methods import Classification, classify


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
async def shelly_rpc(
    device: str, method: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Call any **read-only** RPC method (``*.Get*``/``*.List*``/``*.Check*``) on a device.

    Mutating methods are refused here — use ``shelly_rpc_write``. The method name is
    classified server-side; unknown methods are treated as writes and rejected.
    """
    if classify(method) is not Classification.READ:
        return {
            "error": (
                f"'{method}' is not a read-only method. Use shelly_rpc_write (it gates "
                f"mutations behind confirm:true)."
            ),
            "classification": classify(method).value,
        }
    backend = await get_registry().get_backend(device)
    try:
        return await backend.call(method, params)
    except BackendError as exc:
        return {"device": device, "method": method, "error": str(exc)}


@mcp.tool(annotations={"destructiveHint": True, "openWorldHint": True})
async def shelly_rpc_write(
    device: str,
    method: str,
    params: dict[str, Any] | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Call any **mutating** RPC method. Requires ``confirm:true``; audit-logged.

    Read methods are rejected (use ``shelly_rpc``). Destructive methods (factory reset,
    wipe-all, reset-wifi) need a second gate: ``params.i_understand_data_loss = true``.
    """
    classification = classify(method)
    if classification is Classification.READ:
        return {"error": f"'{method}' is a read method — use shelly_rpc instead."}

    if classification is Classification.DESTRUCTIVE and not (params or {}).get(
        "i_understand_data_loss"
    ):
        return {
            "confirmed": False,
            "destructive": True,
            "message": (
                f"'{method}' is IRREVERSIBLE (data loss). To proceed, set confirm=true AND "
                f"params.i_understand_data_loss=true."
            ),
        }

    if not confirm:
        return confirm_refusal(device, method, params)

    call_params = {k: v for k, v in (params or {}).items() if k != "i_understand_data_loss"}
    try:
        result = await execute_and_audit(device, method, call_params)
    except BackendError as exc:
        return {"device": device, "method": method, "error": str(exc), "confirmed": True}
    return {"device": device, "method": method, "confirmed": True, "result": result}


@mcp.tool(annotations={"readOnlyHint": True})
async def shelly_list_methods(device: str) -> dict[str, Any]:
    """List the RPC methods a device supports (Gen2+ ``Shelly.ListMethods``).

    Returns an actionable error on Gen1/cloud where the device can't enumerate methods.
    """
    backend = await get_registry().get_backend(device)
    try:
        result = await backend.call("Shelly.ListMethods")
    except BackendError as exc:
        return {"device": device, "methods": [], "error": str(exc)}
    methods = result.get("methods", result) if isinstance(result, dict) else result
    return {"device": device, "methods": methods}
