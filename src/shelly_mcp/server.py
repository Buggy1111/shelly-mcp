"""FastMCP application entry point.

Tools are registered here (read tools land in M1, control in M2, etc.). For now
this wires up the server and the ``shelly-mcp`` console entry point so the package
is runnable end-to-end while the backends/tools are built out.
"""

from __future__ import annotations

from fastmcp import FastMCP

from shelly_mcp import __version__

mcp: FastMCP = FastMCP(
    name="shelly-mcp",
    instructions=(
        "Control and automate Shelly smart-home devices (Gen1-Gen4 + BLU), local-first. "
        "Read tools are safe; mutating tools require confirm:true. "
        "Unofficial community project, not affiliated with Allterco/Shelly."
    ),
)


@mcp.tool
def shelly_version() -> dict[str, str]:
    """Return the shelly-mcp server version (health check)."""
    return {"name": "shelly-mcp", "version": __version__}


def main() -> None:
    """Console entry point: run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
