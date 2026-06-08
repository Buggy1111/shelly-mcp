"""System tools — reboot / firmware update / auth, all destructive-gated (D + confirm).

These change the device itself, so each requires ``confirm:true`` and is audit-logged.
``set_auth`` validates password strength and is write-only — a password is never echoed
back or logged (the audit layer redacts it).
"""

from __future__ import annotations

from typing import Any

from shelly_mcp.app import confirm_refusal, execute_and_audit, mcp
from shelly_mcp.backends.base import BackendError

_MIN_PASSWORD_LEN = 12


@mcp.tool(annotations={"destructiveHint": True})
async def shelly_system_reboot(
    device: str, confirm: bool = False, delay_ms: int | None = None
) -> dict[str, Any]:
    """Reboot a device. Requires ``confirm:true``. Audit-logged."""
    params: dict[str, Any] = {}
    if delay_ms is not None:
        params["delay_ms"] = delay_ms
    if not confirm:
        return confirm_refusal(device, "Shelly.Reboot", params)
    try:
        await execute_and_audit(device, "Shelly.Reboot", params)
    except BackendError as exc:
        return {"device": device, "ok": False, "error": str(exc)}
    return {"device": device, "ok": True, "restart_required": True}


@mcp.tool(annotations={"destructiveHint": True})
async def shelly_system_update(
    device: str, confirm: bool = False, channel: str = "stable"
) -> dict[str, Any]:
    """Trigger a firmware update (``channel`` = stable|beta). Requires ``confirm:true``."""
    if channel not in ("stable", "beta"):
        return {"error": "channel must be 'stable' or 'beta'"}
    params = {"stage": channel}
    if not confirm:
        return confirm_refusal(device, "Shelly.Update", params)
    try:
        await execute_and_audit(device, "Shelly.Update", params)
    except BackendError as exc:
        return {"device": device, "ok": False, "error": str(exc)}
    return {"device": device, "ok": True, "channel": channel}


@mcp.tool(annotations={"destructiveHint": True})
async def shelly_system_set_auth(
    device: str, password: str, confirm: bool = False
) -> dict[str, Any]:
    """Enable/rotate the device login password (≥12 chars). Requires ``confirm:true``.

    The password is write-only — never returned, and redacted in the audit log.
    """
    if len(password) < _MIN_PASSWORD_LEN:
        return {"error": f"password must be at least {_MIN_PASSWORD_LEN} characters"}
    if not confirm:
        # Preview must not echo the secret.
        return confirm_refusal(device, "Shelly.SetAuth", {"password": "***"})
    try:
        await execute_and_audit(device, "Shelly.SetAuth", {"user": "admin", "password": password})
    except BackendError as exc:
        return {"device": device, "ok": False, "error": str(exc)}
    return {"device": device, "ok": True}
