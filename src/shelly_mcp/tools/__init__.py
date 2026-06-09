"""Tool groups (vertical slices). Importing this package registers every tool on ``mcp``.

Each submodule attaches its tools to the shared FastMCP instance from
:mod:`shelly_mcp.app` at import time, so importing :mod:`shelly_mcp.tools` wires up the
whole surface.
"""

from __future__ import annotations

from shelly_mcp.tools import (
    control,
    energy,
    generic,
    read,
    resources,
    scenes,
    schedule,
    system,
)

__all__ = [
    "read",
    "control",
    "energy",
    "generic",
    "resources",
    "scenes",
    "schedule",
    "system",
]
