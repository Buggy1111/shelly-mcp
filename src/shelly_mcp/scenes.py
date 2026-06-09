"""Named scenes: the data model + on-disk store (ADR-007, docs/06-SCENES.md).

A scene is a saved, named, ordered batch of ``{device, method, params}`` — the same shape
``Schedule.Create``'s ``calls`` and ``execute_and_audit`` already use, so running one needs
no new execution path. Scenes live in their own YAML file (default
``~/.config/shelly-mcp/scenes.yaml``, env ``SHELLY_MCP_SCENES``), deliberately *separate*
from the secret-bearing ``config.yaml``: there are no secrets here, so the file is safe to
rewrite atomically and a human can still hand-edit it.

Reads are **fail-soft** (a missing or corrupt file yields no scenes, logged, never a crash —
mirrors discovery's passive posture); writes are **atomic** (temp file + ``os.replace``).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

_log = logging.getLogger(__name__)


class SceneAction(BaseModel):
    """One step of a scene: a mutating call on one device (resolved at run time)."""

    device: str = Field(description="Friendly device name/alias — resolved when the scene runs")
    method: str = Field(description="Canonical RPC method, e.g. 'Switch.Set'")
    params: dict[str, Any] = Field(default_factory=dict)


class Scene(BaseModel):
    """An ordered, named set of actions. At least one action."""

    description: str | None = None
    actions: list[SceneAction] = Field(min_length=1)


class SceneFile(BaseModel):
    """The whole scenes file: name -> Scene."""

    scenes: dict[str, Scene] = Field(default_factory=dict)


def scenes_path(path: Path | None = None) -> Path:
    """Resolve the scenes file path: explicit arg > ``$SHELLY_MCP_SCENES`` > XDG default."""
    if path is not None:
        return path
    env = os.environ.get("SHELLY_MCP_SCENES")
    if env:
        return Path(env).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME", "~/.config")
    return Path(base).expanduser() / "shelly-mcp" / "scenes.yaml"


def load_scenes(path: Path | None = None) -> SceneFile:
    """Load scenes. Fail-soft: a missing/corrupt/invalid file → empty (logged), never raises."""
    p = scenes_path(path)
    if not p.exists():
        return SceneFile()
    try:
        raw = yaml.safe_load(p.read_text()) or {}
        return SceneFile.model_validate(raw)
    except (yaml.YAMLError, ValidationError, OSError) as exc:
        _log.warning("Ignoring unreadable scenes file %s: %s", p, exc)
        return SceneFile()


def save_scenes(sf: SceneFile, path: Path | None = None) -> None:
    """Persist scenes atomically (temp file + ``os.replace``). Creates parent dirs."""
    p = scenes_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = sf.model_dump(exclude_none=True)
    tmp = p.with_name(f".{p.name}.tmp")
    tmp.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=True))
    os.replace(tmp, p)
