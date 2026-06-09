"""Webhook tools — outbound HTTP actions on device events (Gen2+, local-only).

A webhook fires up to 5 URLs when a component event happens (e.g. ``switch.on``). Cloud
can't manage them (UnsupportedOnCloud). List is safe; create/update are audited; delete
is confirm-gated. ``cid`` is the component id the event belongs to (e.g. switch ``0``).
"""

from __future__ import annotations

from typing import Any

from shelly_mcp.app import confirm_refusal, execute_and_audit, get_registry, mcp
from shelly_mcp.backends.base import BackendError

_MAX_URLS = 5


def _validate_urls(urls: list[str]) -> str | None:
    if not urls or not isinstance(urls, list):
        return "urls must be a non-empty list of 1-5 URL strings"
    if len(urls) > _MAX_URLS:
        return f"a webhook allows at most {_MAX_URLS} urls (got {len(urls)})"
    if not all(isinstance(u, str) and u for u in urls):
        return "every url must be a non-empty string"
    return None


@mcp.tool(annotations={"readOnlyHint": True})
async def shelly_webhook_list(device: str) -> dict[str, Any]:
    """List webhooks configured on a device. Local-only."""
    backend = await get_registry().get_backend(device)
    try:
        result = await backend.call("Webhook.List")
    except BackendError as exc:
        return {"device": device, "hooks": [], "error": str(exc)}
    hooks = result.get("hooks", []) if isinstance(result, dict) else []
    return {"device": device, "hooks": hooks}


@mcp.tool(annotations={"idempotentHint": True})
async def shelly_webhook_create(
    device: str,
    event: str,
    cid: int,
    urls: list[str],
    enable: bool = True,
    name: str | None = None,
    condition: str | None = None,
    repeat_period: int | None = None,
) -> dict[str, Any]:
    """Create a webhook: ``event`` (e.g. 'switch.on'), ``cid`` component id, ``urls`` 1-5.

    Optional ``condition`` (JS expression) and ``repeat_period`` (seconds; 0=always,
    negative=once). Audit-logged.
    """
    if (err := _validate_urls(urls)) is not None:
        return {"error": err}
    params: dict[str, Any] = {"event": event, "cid": cid, "urls": urls, "enable": enable}
    for field, val in (("name", name), ("condition", condition), ("repeat_period", repeat_period)):
        if val is not None:
            params[field] = val
    try:
        result = await execute_and_audit(device, "Webhook.Create", params)
    except BackendError as exc:
        return {"device": device, "error": str(exc)}
    return {"device": device, "created": result}


@mcp.tool(annotations={"idempotentHint": True})
async def shelly_webhook_update(
    device: str,
    id: int,
    urls: list[str] | None = None,
    enable: bool | None = None,
    name: str | None = None,
    condition: str | None = None,
    repeat_period: int | None = None,
) -> dict[str, Any]:
    """Update fields of an existing webhook by ``id``. Audit-logged."""
    if urls is not None and (err := _validate_urls(urls)) is not None:
        return {"error": err}
    params: dict[str, Any] = {"id": id}
    for field, val in (
        ("urls", urls), ("enable", enable), ("name", name),
        ("condition", condition), ("repeat_period", repeat_period),
    ):
        if val is not None:
            params[field] = val
    try:
        result = await execute_and_audit(device, "Webhook.Update", params)
    except BackendError as exc:
        return {"device": device, "error": str(exc)}
    return {"device": device, "updated": result}


@mcp.tool(annotations={"destructiveHint": True})
async def shelly_webhook_delete(device: str, id: int, confirm: bool = False) -> dict[str, Any]:
    """Delete a webhook by ``id``. Requires ``confirm:true``. Audit-logged."""
    if not confirm:
        return confirm_refusal(device, "Webhook.Delete", {"id": id})
    try:
        result = await execute_and_audit(device, "Webhook.Delete", {"id": id})
    except BackendError as exc:
        return {"device": device, "error": str(exc)}
    return {"device": device, "deleted": result, "confirmed": True}
