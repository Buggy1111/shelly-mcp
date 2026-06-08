"""FastMCP application entry point.

The ``mcp`` instance and shared state live in :mod:`shelly_mcp.app`; the tools live in
:mod:`shelly_mcp.tools` (one module per group). Importing ``tools`` here registers the
whole surface. This module just exposes ``mcp``/``main`` and the test-wiring helpers.

Read tools are safe (``readOnlyHint``); the generic write tool and destructive system
tools gate on ``confirm:true`` (LLM06 — no destructive action without explicit human
approval).
"""

from __future__ import annotations

from shelly_mcp import tools  # noqa: F401  (import registers all tools on `mcp`)
from shelly_mcp.app import get_audit, get_registry, mcp, set_audit, set_registry

__all__ = ["mcp", "main", "get_registry", "set_registry", "get_audit", "set_audit"]


def main() -> None:
    """Console entry point: run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
