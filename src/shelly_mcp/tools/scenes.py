"""Scene tools — define, inspect, and run server-side named scenes (ADR-007).

A scene is a saved, named, ordered batch of ``{device, method, params}`` (see
:mod:`shelly_mcp.scenes`). Running one is **best-effort sequential**: every action is
attempted in order via ``execute_and_audit``, and the result reports per-action ok/error
plus an overall ``ok|partial|failed`` status — physical actions aren't transactional, so we
never pretend a half-done scene succeeded (``[[feedback_thorough_verify]]``).

Definitions are validated at create time — every method must be a **non-destructive WRITE**
and every device must be **known** — so a scheduled, LLM-runnable scene can't become a
backdoor to a destructive method (LLM06/ASI02). Because scenes are non-destructive by
construction, ``scene_run`` needs no confirm gate.
"""

from __future__ import annotations

from typing import Any

from shelly_mcp.app import execute_and_audit, get_registry, mcp
from shelly_mcp.backends.base import BackendError
from shelly_mcp.methods import Classification, classify
from shelly_mcp.scenes import Scene, SceneAction, load_scenes, save_scenes


def _validate_actions(
    actions: list[dict[str, Any]], known: set[str]
) -> tuple[str | None, list[SceneAction], list[str]]:
    """Validate raw action dicts. Returns ``(error_or_None, parsed_actions, warnings)``."""
    if not actions or not isinstance(actions, list):
        return "actions must be a non-empty list of {device, method, params}", [], []
    parsed: list[SceneAction] = []
    warnings: list[str] = []
    for i, action in enumerate(actions):
        if not isinstance(action, dict):
            return f"action #{i} must be an object with device + method", [], []
        device = action.get("device")
        method = action.get("method")
        params = action.get("params", {})
        if not isinstance(device, str) or not device:
            return f"action #{i} needs a 'device' name", [], []
        if not isinstance(method, str) or not method:
            return f"action #{i} needs a 'method' string", [], []
        if not isinstance(params, dict):
            return f"action #{i} 'params' must be an object", [], []
        cls = classify(method)
        if cls is Classification.READ:
            return f"action #{i}: '{method}' is a read — a scene must change device state", [], []
        if cls is Classification.DESTRUCTIVE:
            return f"action #{i}: '{method}' is destructive and not allowed in a scene", [], []
        if device not in known:
            return f"action #{i}: unknown device '{device}' (known: {sorted(known)})", [], []
        if method.rsplit(".", 1)[-1] == "Toggle":
            warnings.append(
                f"action #{i} uses '{method}' — Toggle isn't idempotent; "
                f"running the scene twice undoes it. Prefer an absolute Set."
            )
        parsed.append(SceneAction(device=device, method=method, params=params))
    return None, parsed, warnings


@mcp.tool(annotations={"readOnlyHint": True})
async def shelly_scene_list() -> dict[str, Any]:
    """List defined scenes (name, description, action count). Read-only."""
    sf = load_scenes()
    return {
        "scenes": [
            {"name": name, "description": scene.description, "actions": len(scene.actions)}
            for name, scene in sf.scenes.items()
        ]
    }


@mcp.tool(annotations={"readOnlyHint": True})
async def shelly_scene_get(name: str) -> dict[str, Any]:
    """Show a scene's full definition (its ordered actions). Read-only."""
    sf = load_scenes()
    scene = sf.scenes.get(name)
    if scene is None:
        return {"error": f"no scene named '{name}'", "available": list(sf.scenes)}
    return {
        "name": name,
        "description": scene.description,
        "actions": [a.model_dump() for a in scene.actions],
    }


@mcp.tool(annotations={"idempotentHint": True})
async def shelly_scene_create(
    name: str,
    actions: list[dict[str, Any]],
    description: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Define (save) a named scene from an ordered list of ``{device, method, params}``.

    Every method must be a non-destructive mutating method; every device must be known.
    Fails if the name already exists unless ``overwrite=true``. Prefer absolute ``Set``
    methods over ``Toggle`` so the scene is safe to run twice (you'll get a warning otherwise).
    """
    if not name or not isinstance(name, str):
        return {"error": "scene name must be a non-empty string"}
    known = get_registry().known_devices()
    err, parsed, warnings = _validate_actions(actions, known)
    if err is not None:
        return {"error": err}
    sf = load_scenes()
    if name in sf.scenes and not overwrite:
        return {"error": f"scene '{name}' already exists — pass overwrite=true to replace it"}
    sf.scenes[name] = Scene(description=description, actions=parsed)
    save_scenes(sf)
    out: dict[str, Any] = {"saved": name, "actions": len(parsed)}
    if warnings:
        out["warnings"] = warnings
    return out


@mcp.tool
async def shelly_scene_run(name: str) -> dict[str, Any]:
    """Run a named scene: attempt every action in order, report per-action results.

    Best-effort and sequential — a failing action does **not** abort the rest. ``status`` is
    ``ok`` (all succeeded), ``partial`` (some failed), or ``failed`` (none succeeded). A
    partial run can simply be re-run later to finish it (scenes use absolute states, so
    re-running is safe). Every action is audit-logged.
    """
    sf = load_scenes()
    scene = sf.scenes.get(name)
    if scene is None:
        return {"error": f"no scene named '{name}'", "available": list(sf.scenes)}

    results: list[dict[str, Any]] = []
    ok_count = 0
    for action in scene.actions:
        entry: dict[str, Any] = {"device": action.device, "method": action.method}
        try:
            await execute_and_audit(action.device, action.method, action.params)
            entry["ok"] = True
            ok_count += 1
        except BackendError as exc:
            entry["ok"] = False
            entry["error"] = str(exc)
        results.append(entry)

    total = len(results)
    status = "ok" if ok_count == total else "failed" if ok_count == 0 else "partial"
    return {"scene": name, "status": status, "ok": ok_count, "total": total, "results": results}


@mcp.tool(annotations={"destructiveHint": True})
async def shelly_scene_delete(name: str, confirm: bool = False) -> dict[str, Any]:
    """Delete a named scene. Requires ``confirm:true``."""
    sf = load_scenes()
    if name not in sf.scenes:
        return {"error": f"no scene named '{name}'", "available": list(sf.scenes)}
    if not confirm:
        return {
            "confirmed": False,
            "would_delete": name,
            "message": f"This will delete scene '{name}'. Re-call with confirm=true to proceed.",
        }
    del sf.scenes[name]
    save_scenes(sf)
    return {"deleted": name, "confirmed": True}
