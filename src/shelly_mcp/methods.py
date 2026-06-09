"""Method registry: classification (READ/WRITE/DESTRUCTIVE) + Gen1 REST mapping.

This is the security spine of the generic ``rpc`` engine (docs/03-SECURITY §5.1):

* ``shelly_rpc`` accepts only ``READ`` methods.
* ``shelly_rpc_write`` accepts ``WRITE``/``DESTRUCTIVE`` and enforces ``confirm:true``;
  ``DESTRUCTIVE`` (factory reset / wipe-all / reset-wifi) needs a second
  ``i_understand_data_loss`` gate.
* An **unknown** Gen2+ method defaults to ``WRITE`` — fail-safe, never silently READ.

The Gen2 JSON-RPC naming convention is regular enough to classify by verb; a small
explicit set marks the irreversible methods. The Gen1 REST mapping translates the
canonical (Gen2-style) method names a tool emits into Gen1 ``/relay``/``/light``/
``/roller`` URLs so the Gen1 backend and the classifier share one source of truth.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from urllib.parse import urlencode

from shelly_mcp.backends.base import UnsupportedOnGeneration


class Classification(StrEnum):
    """How dangerous a method is. Drives which tool may call it and what gating applies."""

    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"


# Verb prefixes (the part after the last '.') that are always safe reads.
_READ_PREFIXES = ("Get", "List", "Check")
# Whole-method reads that don't start with a read prefix.
_READ_EXACT = frozenset({"Wifi.Scan"})
# Irreversible / data-loss methods — the double-gated set.
_DESTRUCTIVE_EXACT = frozenset(
    {
        "Shelly.FactoryReset",
        "Shelly.ResetWiFiConfig",
        "Matter.FactoryReset",
        "Schedule.DeleteAll",
        "EMData.DeleteAllData",
        "EM1Data.DeleteAllData",
        "EM1.RevertToFactoryCalibration",
    }
)
# Suffixes that make any method irreversible regardless of component.
_DESTRUCTIVE_SUFFIXES = ("FactoryReset", "DeleteAllData", "DeleteAll", "ResetWiFiConfig")


def _action(method: str) -> str:
    """The verb part of a ``Component.Action`` method (or the whole string)."""
    return method.rsplit(".", 1)[-1] if "." in method else method


def classify(method: str) -> Classification:
    """Classify a Gen2+ RPC method. Unknown → WRITE (fail-safe, never silently READ)."""
    if method in _READ_EXACT:
        return Classification.READ
    if method in _DESTRUCTIVE_EXACT or method.endswith(_DESTRUCTIVE_SUFFIXES):
        return Classification.DESTRUCTIVE
    if _action(method).startswith(_READ_PREFIXES):
        return Classification.READ
    return Classification.WRITE


def is_read(method: str) -> bool:
    return classify(method) is Classification.READ


def requires_data_loss_ack(method: str) -> bool:
    """True if the method is irreversible and needs the ``i_understand_data_loss`` gate."""
    return classify(method) is Classification.DESTRUCTIVE


# --------------------------------------------------------------------------- Gen1
# Canonical (Gen2-style) method -> Gen1 REST. Each entry yields (path, query-dict).
# Gen1 control is all HTTP GET with query params; reads hit /status or /settings.


def gen1_rest_for(method: str, params: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    """Translate a canonical method + params into a Gen1 ``(path, query)`` REST call.

    Raises :class:`UnsupportedOnGeneration` for methods Gen1 hardware can't express
    via REST (most config/automation RPC) — the caller should surface that honestly.
    """
    p = dict(params or {})
    ch = int(p.get("id", 0))

    if method in ("Shelly.GetStatus", "Switch.GetStatus", "Light.GetStatus",
                  "RGB.GetStatus", "RGBW.GetStatus", "CCT.GetStatus", "Cover.GetStatus"):
        return "/status", {}
    if method in ("Shelly.GetConfig", "Sys.GetConfig"):
        return "/settings", {}

    if method == "Switch.Set":
        q: dict[str, Any] = {"turn": "on" if p.get("on") else "off"}
        if p.get("toggle_after") is not None:
            q["timer"] = p["toggle_after"]
        return f"/relay/{ch}", q
    if method == "Switch.Toggle":
        return f"/relay/{ch}", {"turn": "toggle"}

    if method in ("Light.Set", "RGB.Set", "RGBW.Set", "CCT.Set"):
        q = {}
        if "on" in p:
            q["turn"] = "on" if p["on"] else "off"
        rgb = p.get("rgb")
        is_color = isinstance(rgb, (list, tuple)) and len(rgb) == 3
        if isinstance(rgb, (list, tuple)) and len(rgb) == 3:
            q["red"], q["green"], q["blue"] = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
        if p.get("white") is not None:
            q["white"] = int(p["white"])
        if p.get("temp_k") is not None:
            q["temp"] = int(p["temp_k"])
        if p.get("brightness") is not None:
            # Gen1: colour brightness is 'gain', plain/white dimmer is 'brightness'.
            q["gain" if is_color else "brightness"] = int(p["brightness"])
        # Colour bulbs use /color/N, white-only/dimmers use /light/N or /white/N.
        path = f"/color/{ch}" if is_color else f"/light/{ch}"
        return path, q

    if method in ("Cover.Open", "Cover.Close", "Cover.Stop"):
        go = {"Cover.Open": "open", "Cover.Close": "close", "Cover.Stop": "stop"}[method]
        return f"/roller/{ch}", {"go": go}
    if method == "Cover.GoToPosition":
        return f"/roller/{ch}", {"go": "to_pos", "roller_pos": int(p.get("pos", 0))}

    raise UnsupportedOnGeneration(
        f"'{method}' has no Gen1 REST equivalent — this needs a Gen2+ device "
        f"(Gen1 hardware can't express it over its HTTP API)."
    )


def gen1_url(path: str, query: dict[str, Any]) -> str:
    """Build a relative Gen1 URL (path + encoded query) for logging/debugging."""
    return f"{path}?{urlencode(query)}" if query else path
