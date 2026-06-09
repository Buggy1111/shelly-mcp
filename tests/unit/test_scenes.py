"""Tests for named scenes — store (round-trip / atomic / fail-soft) + the 5 tools.

Covers the design's Definition of Done (docs/06-SCENES.md §10): CRUD round-trip, atomic
write, corrupt-file fail-soft, validation (unknown device / READ / DESTRUCTIVE rejected,
Toggle warning, overwrite guard), and run with ok|partial|failed paths against fakes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from shelly_mcp.scenes import Scene, SceneAction, SceneFile, load_scenes, save_scenes
from shelly_mcp.tools.scenes import (
    shelly_scene_create,
    shelly_scene_delete,
    shelly_scene_get,
    shelly_scene_list,
    shelly_scene_run,
)

_FILM = [
    {"device": "dev", "method": "Switch.Set", "params": {"id": 0, "on": False}},
    {"device": "dev", "method": "Light.Set", "params": {"id": 0, "brightness": 15}},
]


# ----------------------------------------------------------------- store layer
def test_store_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "scenes.yaml"
    sf = SceneFile(scenes={"film": Scene(actions=[SceneAction(device="dev", method="Switch.Set")])})
    save_scenes(sf, path)
    assert path.exists()
    loaded = load_scenes(path)
    assert "film" in loaded.scenes
    assert loaded.scenes["film"].actions[0].method == "Switch.Set"


def test_store_missing_file_is_empty(tmp_path: Path) -> None:
    assert load_scenes(tmp_path / "nope.yaml").scenes == {}


def test_store_corrupt_file_fails_soft(tmp_path: Path) -> None:
    path = tmp_path / "scenes.yaml"
    path.write_text("scenes: [this is not a mapping of scenes")  # invalid YAML
    assert load_scenes(path).scenes == {}  # no crash, empty


def test_store_invalid_schema_fails_soft(tmp_path: Path) -> None:
    path = tmp_path / "scenes.yaml"
    path.write_text("scenes:\n  bad:\n    actions: []\n")  # actions must be non-empty
    assert load_scenes(path).scenes == {}


def test_store_write_is_atomic_no_temp_left(tmp_path: Path) -> None:
    path = tmp_path / "scenes.yaml"
    sf = SceneFile(scenes={"a": Scene(actions=[SceneAction(device="dev", method="X.Set")])})
    save_scenes(sf, path)
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "scenes.yaml"]
    assert leftovers == []  # temp file was renamed away


# ------------------------------------------------------------------- create
async def test_create_and_get_round_trip(wire: Any, scenes_file: Path) -> None:
    out = await shelly_scene_create.fn(name="film", actions=_FILM, description="Movie night")
    assert out["saved"] == "film"
    assert out["actions"] == 2
    got = await shelly_scene_get.fn(name="film")
    assert got["description"] == "Movie night"
    assert [a["method"] for a in got["actions"]] == ["Switch.Set", "Light.Set"]


async def test_create_rejects_unknown_device(wire: Any, scenes_file: Path) -> None:
    out = await shelly_scene_create.fn(
        name="x", actions=[{"device": "ghost", "method": "Switch.Set"}]
    )
    assert "error" in out and "unknown device" in out["error"]


async def test_create_rejects_read_method(wire: Any, scenes_file: Path) -> None:
    out = await shelly_scene_create.fn(
        name="x", actions=[{"device": "dev", "method": "Shelly.GetStatus"}]
    )
    assert "error" in out and "read" in out["error"]


async def test_create_rejects_destructive_method(wire: Any, scenes_file: Path) -> None:
    out = await shelly_scene_create.fn(
        name="x", actions=[{"device": "dev", "method": "Shelly.FactoryReset"}]
    )
    assert "error" in out and "destructive" in out["error"]


async def test_create_warns_on_toggle(wire: Any, scenes_file: Path) -> None:
    out = await shelly_scene_create.fn(
        name="x", actions=[{"device": "dev", "method": "Switch.Toggle"}]
    )
    assert out["saved"] == "x"
    assert "warnings" in out and "Toggle" in out["warnings"][0]


async def test_create_rejects_empty_actions(wire: Any, scenes_file: Path) -> None:
    assert "error" in await shelly_scene_create.fn(name="x", actions=[])


async def test_create_overwrite_guard(wire: Any, scenes_file: Path) -> None:
    await shelly_scene_create.fn(name="film", actions=_FILM)
    blocked = await shelly_scene_create.fn(name="film", actions=_FILM)
    assert "error" in blocked and "already exists" in blocked["error"]
    ok = await shelly_scene_create.fn(name="film", actions=_FILM, overwrite=True)
    assert ok["saved"] == "film"


async def test_create_rejects_blank_name(wire: Any, scenes_file: Path) -> None:
    assert "error" in await shelly_scene_create.fn(name="", actions=_FILM)


# --------------------------------------------------------------------- list
async def test_list_reports_counts(wire: Any, scenes_file: Path) -> None:
    await shelly_scene_create.fn(name="film", actions=_FILM)
    out = await shelly_scene_list.fn()
    assert out["scenes"] == [{"name": "film", "description": None, "actions": 2}]


async def test_get_unknown_scene(wire: Any, scenes_file: Path) -> None:
    out = await shelly_scene_get.fn(name="nope")
    assert "error" in out and out["available"] == []


# ---------------------------------------------------------------------- run
async def test_run_all_ok(wire: Any, scenes_file: Path) -> None:
    await shelly_scene_create.fn(name="film", actions=_FILM)
    out = await shelly_scene_run.fn(name="film")
    assert out["status"] == "ok"
    assert out["ok"] == 2 and out["total"] == 2
    assert all(r["ok"] for r in out["results"])
    # the actions actually reached the backend, in order
    assert [m for m, _ in wire.calls] == ["Switch.Set", "Light.Set"]


async def test_run_partial(wire: Any, scenes_file: Path) -> None:
    wire.fail_methods.add("Light.Set")
    await shelly_scene_create.fn(name="film", actions=_FILM)
    out = await shelly_scene_run.fn(name="film")
    assert out["status"] == "partial"
    assert out["ok"] == 1 and out["total"] == 2
    failed = [r for r in out["results"] if not r["ok"]]
    assert failed[0]["method"] == "Light.Set" and "error" in failed[0]


async def test_run_failed(wire: Any, scenes_file: Path) -> None:
    wire.fail_methods.update({"Switch.Set", "Light.Set"})
    await shelly_scene_create.fn(name="film", actions=_FILM)
    out = await shelly_scene_run.fn(name="film")
    assert out["status"] == "failed"
    assert out["ok"] == 0


async def test_run_continues_past_failure(wire: Any, scenes_file: Path) -> None:
    # First action fails — the rest must still run (best-effort, no abort).
    wire.fail_methods.add("Switch.Set")
    await shelly_scene_create.fn(name="film", actions=_FILM)
    await shelly_scene_run.fn(name="film")
    assert "Light.Set" in [m for m, _ in wire.calls]  # ran despite the earlier failure


async def test_run_audits_actions(wire: Any, scenes_file: Path, tmp_path: Path) -> None:
    await shelly_scene_create.fn(name="film", actions=_FILM)
    await shelly_scene_run.fn(name="film")
    audit_text = (tmp_path / "audit.jsonl").read_text()
    assert "Switch.Set" in audit_text and "Light.Set" in audit_text


async def test_run_unknown_scene(wire: Any, scenes_file: Path) -> None:
    out = await shelly_scene_run.fn(name="nope")
    assert "error" in out


# ------------------------------------------------------------------- delete
async def test_delete_confirm_gate(wire: Any, scenes_file: Path) -> None:
    await shelly_scene_create.fn(name="film", actions=_FILM)
    refused = await shelly_scene_delete.fn(name="film")
    assert refused["confirmed"] is False
    assert refused["would_delete"] == "film"  # preview names the scene, not a device
    assert "film" in load_scenes(scenes_file).scenes  # still there
    ok = await shelly_scene_delete.fn(name="film", confirm=True)
    assert ok["deleted"] == "film"
    assert "film" not in load_scenes(scenes_file).scenes


async def test_delete_unknown_scene(wire: Any, scenes_file: Path) -> None:
    assert "error" in await shelly_scene_delete.fn(name="nope", confirm=True)
