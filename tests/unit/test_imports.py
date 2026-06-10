"""Every module must import cleanly on its own — no latent circular imports.

``import shelly_mcp.methods`` used to fail when it was the FIRST import in a
process (methods → backends/__init__ eagerly pulled gen1_rest, which needs
methods back). It only worked by accident of import order through server.py, so
each module is exercised in a fresh interpreter here.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

_MODULES = [
    "shelly_mcp.methods",
    "shelly_mcp.backends",
    "shelly_mcp.client",
    "shelly_mcp.server",
]


@pytest.mark.parametrize("module", _MODULES)
def test_module_imports_standalone(module: str) -> None:
    proc = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, f"import {module} failed:\n{proc.stderr}"
