"""Script tools — the on-device mJS automation engine (Gen2+, local-only).

Scripts run JavaScript *on the device*. That power is also the risk: uploading or
evaluating code is arbitrary code execution on the device (ASI05/LLM05), so
``put_code`` and ``eval`` are **confirm-gated**, and ``delete`` is too. List / get_code
/ start / stop are lower-stakes (audited where they mutate). Cloud can't manage scripts
(UnsupportedOnCloud).

``PutCode`` has a per-call size limit, so :func:`shelly_script_put_code` chunks large
code automatically (first chunk respects the caller's ``append``; the rest append).
``GetCode`` is paginated, so :func:`shelly_script_get_code` reassembles the full source.
"""

from __future__ import annotations

from typing import Any

from shelly_mcp.app import confirm_refusal, execute_and_audit, get_registry, mcp
from shelly_mcp.backends.base import BackendError

_CHUNK = 1024  # bytes per PutCode call (stay well under the device limit)
_MAX_GET_ITERS = 64  # safety bound on GetCode pagination


@mcp.tool(annotations={"readOnlyHint": True})
async def shelly_script_list(device: str) -> dict[str, Any]:
    """List scripts on a device (id, name, enable, running). Local-only."""
    backend = await get_registry().get_backend(device)
    try:
        result = await backend.call("Script.List")
    except BackendError as exc:
        return {"device": device, "scripts": [], "error": str(exc)}
    scripts = result.get("scripts", []) if isinstance(result, dict) else []
    return {"device": device, "scripts": scripts}


@mcp.tool(annotations={"readOnlyHint": True})
async def shelly_script_get_code(device: str, id: int) -> dict[str, Any]:
    """Get a script's full source, reassembling the device's paginated ``GetCode``."""
    backend = await get_registry().get_backend(device)
    parts: list[str] = []
    offset = 0
    try:
        for _ in range(_MAX_GET_ITERS):
            result = await backend.call("Script.GetCode", {"id": id, "offset": offset})
            if not isinstance(result, dict) or "data" not in result:
                break
            data = result.get("data") or ""
            parts.append(data)
            offset += len(data)
            if not result.get("left"):
                break
    except BackendError as exc:
        return {"device": device, "id": id, "error": str(exc)}
    return {"device": device, "id": id, "code": "".join(parts)}


@mcp.tool(annotations={"idempotentHint": True})
async def shelly_script_create(device: str, name: str | None = None) -> dict[str, Any]:
    """Create an empty script (optionally named). Returns its ``id``. Audit-logged.

    Use ``shelly_script_put_code`` to give it code (that step is confirm-gated).
    """
    params: dict[str, Any] = {}
    if name is not None:
        params["name"] = name
    try:
        result = await execute_and_audit(device, "Script.Create", params)
    except BackendError as exc:
        return {"device": device, "error": str(exc)}
    return {"device": device, "created": result}


@mcp.tool(annotations={"destructiveHint": True})
async def shelly_script_put_code(
    device: str, id: int, code: str, append: bool = False, confirm: bool = False
) -> dict[str, Any]:
    """Upload code into a script (chunked). **Arbitrary code on the device** → ``confirm:true``.

    ``append=false`` replaces the script body; ``true`` appends. Large code is split into
    ≤1 KB chunks automatically. Audit-logged.
    """
    if not code or not isinstance(code, str):
        return {"error": "code must be a non-empty string"}
    if not confirm:
        return confirm_refusal(
            device, "Script.PutCode", {"id": id, "bytes": len(code), "append": append}
        )
    chunks = [code[i : i + _CHUNK] for i in range(0, len(code), _CHUNK)]
    total = None
    try:
        for n, chunk in enumerate(chunks):
            # First chunk honours the caller's append; subsequent chunks must append.
            chunk_append = append if n == 0 else True
            result = await execute_and_audit(
                device, "Script.PutCode", {"id": id, "code": chunk, "append": chunk_append}
            )
            if isinstance(result, dict):
                total = result.get("len", total)
    except BackendError as exc:
        return {"device": device, "id": id, "error": str(exc), "confirmed": True}
    return {"device": device, "id": id, "chunks": len(chunks), "len": total, "confirmed": True}


@mcp.tool
async def shelly_script_start(device: str, id: int) -> dict[str, Any]:
    """Start a script by ``id``. Returns ``was_running``. Audit-logged."""
    try:
        result = await execute_and_audit(device, "Script.Start", {"id": id})
    except BackendError as exc:
        return {"device": device, "id": id, "error": str(exc)}
    return {"device": device, "id": id, "started": result}


@mcp.tool
async def shelly_script_stop(device: str, id: int) -> dict[str, Any]:
    """Stop a script by ``id``. Returns ``was_running``. Audit-logged."""
    try:
        result = await execute_and_audit(device, "Script.Stop", {"id": id})
    except BackendError as exc:
        return {"device": device, "id": id, "error": str(exc)}
    return {"device": device, "id": id, "stopped": result}


@mcp.tool(annotations={"destructiveHint": True})
async def shelly_script_eval(
    device: str, id: int, code: str, confirm: bool = False
) -> dict[str, Any]:
    """Evaluate an expression inside a running script. **Arbitrary code** → ``confirm:true``.

    Returns the stringified result. Audit-logged.
    """
    if not code or not isinstance(code, str):
        return {"error": "code must be a non-empty string"}
    if not confirm:
        return confirm_refusal(device, "Script.Eval", {"id": id, "code": code})
    try:
        result = await execute_and_audit(device, "Script.Eval", {"id": id, "code": code})
    except BackendError as exc:
        return {"device": device, "id": id, "error": str(exc), "confirmed": True}
    return {"device": device, "id": id, "result": result, "confirmed": True}


@mcp.tool(annotations={"destructiveHint": True})
async def shelly_script_delete(device: str, id: int, confirm: bool = False) -> dict[str, Any]:
    """Delete a script by ``id``. Requires ``confirm:true``. Audit-logged."""
    if not confirm:
        return confirm_refusal(device, "Script.Delete", {"id": id})
    try:
        result = await execute_and_audit(device, "Script.Delete", {"id": id})
    except BackendError as exc:
        return {"device": device, "id": id, "error": str(exc), "confirmed": True}
    return {"device": device, "id": id, "deleted": result, "confirmed": True}
