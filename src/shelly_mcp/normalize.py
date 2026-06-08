"""Normalizer — raw per-generation status → canonical models (volatile boundary #2).

This is where Gen1's ``relays[]/meters[]/lights[]/rollers[]`` arrays and Gen2+'s
``switch:0``/``rgbw:0``/``cover:0`` component dicts collapse into one consistent
world (ADR-003). Tools and the LLM only ever see the canonical shapes from
:mod:`shelly_mcp.models`; this module is the only place that knows the difference.

Energy unit normalization lives here and *must not* leak elsewhere. The unit of
Gen1 ``meters[].total`` is **transport-dependent** (verified against the real
``mycka`` dishwasher plug — see ADR-005):

* **Gen1 ``meters[].total`` over LOCAL ``/status`` is Watt-minutes** — ÷60 for Wh.
* **Gen1 ``meters[].total`` over Shelly CLOUD is already Wh** — the cloud pre-divides
  the device's native Watt-minute counter. Pass through.
* **Gen1 ``emeters[].total`` is already Wh** (both transports) — pass through.
* **Gen2 ``aenergy.total`` is already Wh** — pass through.

A canonical field is ``None`` when the device genuinely can't report it; the raw
component is always attached under ``raw`` so a power user is never blocked.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from shelly_mcp.models import BackendKind, ChannelState, CoverState, Generation, LightState

# Gen2 component-key prefixes we know how to fold into each canonical bucket.
_GEN2_CHANNEL_PREFIXES = ("switch:", "pm1:")
_GEN2_LIGHT_PREFIXES = ("light:", "rgb:", "rgbw:", "cct:")
_GEN2_COVER_PREFIXES = ("cover:",)

# Gen1 roller motion words → canonical CoverState.state vocabulary.
_GEN1_ROLLER_STATE = {"open": "opening", "close": "closing", "stop": "stopped"}


class NormalizedStatus(BaseModel):
    """A whole device's status, folded into canonical buckets keyed by component.

    Keys are the device's *native* component keys (``switch:0`` on Gen2, ``switch:0``
    synthesised from ``relays[0]`` on Gen1) so the same physical channel reads the
    same way regardless of generation.
    """

    channels: dict[str, ChannelState] = Field(default_factory=dict)
    lights: dict[str, LightState] = Field(default_factory=dict)
    covers: dict[str, CoverState] = Field(default_factory=dict)
    device_temp_c: float | None = Field(
        default=None, description="Device-level temperature (Gen1 tmp.tC); None if not reported"
    )


def _f(value: Any) -> float | None:
    """Coerce a numeric-ish value to float, or None (never a fake zero)."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _i(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None


def _nested_total(raw: dict[str, Any], key: str) -> float | None:
    """Pull ``raw[key]['total']`` as float (Gen2 aenergy/ret_aenergy shape)."""
    sub = raw.get(key)
    if isinstance(sub, dict):
        return _f(sub.get("total"))
    return None


def _as_list(value: Any) -> list[Any]:
    """A Gen1 status array, or [] if absent/malformed (keeps mypy + callers honest)."""
    return value if isinstance(value, list) else []


def _meter_total_to_wh(total: Any, *, already_wh: bool) -> float | None:
    """Gen1 ``meters[].total`` → Wh. Watt-minutes over local; already Wh over cloud."""
    value = _f(total)
    if value is None:
        return None
    return value if already_wh else value / 60.0


class Normalizer:
    """Stateless mapper. Static methods so they're trivially unit-testable in isolation."""

    # ------------------------------------------------------------------ channels
    @staticmethod
    def gen2_channel(raw: dict[str, Any]) -> ChannelState:
        """Normalize a Gen2 ``switch:N`` / ``pm1:N`` component. Energy already in Wh."""
        temp = raw.get("temperature")
        return ChannelState(
            output=raw.get("output") if isinstance(raw.get("output"), bool) else None,
            power_w=_f(raw.get("apower")),
            energy_total_wh=_nested_total(raw, "aenergy"),
            ret_energy_total_wh=_nested_total(raw, "ret_aenergy"),
            voltage=_f(raw.get("voltage")),
            current=_f(raw.get("current")),
            pf=_f(raw.get("pf")),
            freq=_f(raw.get("freq")),
            temperature_c=_f(temp.get("tC")) if isinstance(temp, dict) else None,
            source=raw.get("source") if isinstance(raw.get("source"), str) else None,
            raw=raw,
        )

    @staticmethod
    def gen1_channel(
        relay: dict[str, Any] | None,
        meter: dict[str, Any] | None = None,
        *,
        device_temp_c: float | None = None,
        meter_total_is_wh: bool = False,
    ) -> ChannelState:
        """Fold one Gen1 ``relays[i]`` + matching ``meters[i]`` into a ChannelState.

        Gen1 splits switching (``relays[]``) from metering (``meters[]``); we re-join
        them by index. ``meters[].total`` is **Watt-minutes** locally (÷60), but the
        cloud already returns Wh — pass ``meter_total_is_wh=True`` for cloud data.
        """
        relay = relay or {}
        meter = meter or {}
        return ChannelState(
            output=relay.get("ison") if isinstance(relay.get("ison"), bool) else None,
            power_w=_f(meter.get("power")),
            energy_total_wh=_meter_total_to_wh(meter.get("total"), already_wh=meter_total_is_wh),
            voltage=_f(meter.get("voltage")),  # plain meters[] lack it → None
            current=_f(meter.get("current")),
            temperature_c=device_temp_c,
            source=relay.get("source") if isinstance(relay.get("source"), str) else None,
            raw={"relay": relay, "meter": meter},
        )

    @staticmethod
    def gen1_emeter_channel(
        relay: dict[str, Any] | None,
        emeter: dict[str, Any],
        *,
        device_temp_c: float | None = None,
    ) -> ChannelState:
        """Gen1 EM/3EM channel: ``emeters[].total`` is already **Wh** (no ÷60)."""
        relay = relay or {}
        return ChannelState(
            output=relay.get("ison") if isinstance(relay.get("ison"), bool) else None,
            power_w=_f(emeter.get("power")),
            energy_total_wh=_f(emeter.get("total")),
            ret_energy_total_wh=_f(emeter.get("total_returned")),
            voltage=_f(emeter.get("voltage")),
            current=_f(emeter.get("current")),
            pf=_f(emeter.get("pf")),
            temperature_c=device_temp_c,
            source=relay.get("source") if isinstance(relay.get("source"), str) else None,
            raw={"relay": relay, "emeter": emeter},
        )

    # -------------------------------------------------------------------- lights
    @staticmethod
    def gen2_light(raw: dict[str, Any]) -> LightState:
        """Normalize a Gen2 ``light:N``/``rgb:N``/``rgbw:N``/``cct:N`` component."""
        rgb_raw = raw.get("rgb")
        rgb = (
            (int(rgb_raw[0]), int(rgb_raw[1]), int(rgb_raw[2]))
            if isinstance(rgb_raw, (list, tuple)) and len(rgb_raw) == 3
            else None
        )
        return LightState(
            output=raw.get("output") if isinstance(raw.get("output"), bool) else None,
            brightness=_i(raw.get("brightness")),
            rgb=rgb,
            white=_i(raw.get("white")),
            temp_k=_i(raw.get("ct")),  # cct:N reports colour temp as 'ct' (Kelvin)
            power_w=_f(raw.get("apower")),
            energy_total_wh=_nested_total(raw, "aenergy"),
            raw=raw,
        )

    @staticmethod
    def gen1_light(
        raw: dict[str, Any],
        meter: dict[str, Any] | None = None,
        *,
        meter_total_is_wh: bool = False,
    ) -> LightState:
        """Normalize a Gen1 ``lights[i]``.

        Colour mode reports brightness as ``gain`` (0-100) and a ``red/green/blue``
        triple; white mode uses ``brightness`` + ``temp`` (Kelvin). Power, if any,
        comes from the parallel ``meters[i]`` entry (same Wmin/Wh transport rule).
        """
        mode = raw.get("mode")
        is_color = mode == "color"
        rgb = None
        if any(k in raw for k in ("red", "green", "blue")):
            rgb = (_i(raw.get("red")) or 0, _i(raw.get("green")) or 0, _i(raw.get("blue")) or 0)
        meter = meter or {}
        return LightState(
            output=raw.get("ison") if isinstance(raw.get("ison"), bool) else None,
            brightness=_i(raw.get("gain")) if is_color else _i(raw.get("brightness")),
            rgb=rgb if is_color else None,
            white=_i(raw.get("white")),
            temp_k=None if is_color else _i(raw.get("temp")),
            power_w=_f(meter.get("power")),
            energy_total_wh=_meter_total_to_wh(meter.get("total"), already_wh=meter_total_is_wh),
            raw=raw,
        )

    # -------------------------------------------------------------------- covers
    @staticmethod
    def gen2_cover(raw: dict[str, Any]) -> CoverState:
        """Normalize a Gen2 ``cover:N`` (state vocabulary is already canonical)."""
        return CoverState(
            state=raw.get("state") if isinstance(raw.get("state"), str) else None,
            current_pos=_i(raw.get("current_pos")),
            target_pos=_i(raw.get("target_pos")),
            power_w=_f(raw.get("apower")),
            raw=raw,
        )

    @staticmethod
    def gen1_roller(raw: dict[str, Any]) -> CoverState:
        """Normalize a Gen1 ``rollers[i]``; motion words map to canonical states."""
        state = raw.get("state")
        return CoverState(
            state=_GEN1_ROLLER_STATE.get(state, state) if isinstance(state, str) else None,
            current_pos=_i(raw.get("current_pos")),
            power_w=_f(raw.get("power")),
            raw=raw,
        )

    # ----------------------------------------------------------- whole-status fan
    @staticmethod
    def normalize_status(
        status: dict[str, Any], gen: Generation, *, backend: BackendKind = "local_rest"
    ) -> NormalizedStatus:
        """Fold a full raw status payload into canonical buckets.

        ``backend`` matters only for Gen1 energy units: a Gen1 ``meters[].total`` is
        Watt-minutes over ``local_rest`` but already Wh over ``cloud`` (ADR-005).
        """
        if gen.is_rpc:
            return Normalizer._normalize_gen2(status)
        return Normalizer._normalize_gen1(status, meter_total_is_wh=backend == "cloud")

    @staticmethod
    def _normalize_gen2(status: dict[str, Any]) -> NormalizedStatus:
        out = NormalizedStatus()
        for key, val in status.items():
            if not isinstance(val, dict) or ":" not in key:
                continue
            if key.startswith(_GEN2_CHANNEL_PREFIXES):
                out.channels[key] = Normalizer.gen2_channel(val)
            elif key.startswith(_GEN2_LIGHT_PREFIXES):
                out.lights[key] = Normalizer.gen2_light(val)
            elif key.startswith(_GEN2_COVER_PREFIXES):
                out.covers[key] = Normalizer.gen2_cover(val)
        return out

    @staticmethod
    def _normalize_gen1(
        status: dict[str, Any], *, meter_total_is_wh: bool = False
    ) -> NormalizedStatus:
        out = NormalizedStatus()
        tmp = status.get("tmp")
        if isinstance(tmp, dict):
            out.device_temp_c = _f(tmp.get("tC"))
        elif isinstance(status.get("temperature"), (int, float)):
            out.device_temp_c = _f(status.get("temperature"))

        relays = _as_list(status.get("relays"))
        meters = _as_list(status.get("meters"))
        emeters = _as_list(status.get("emeters"))
        lights = _as_list(status.get("lights"))
        rollers = _as_list(status.get("rollers"))

        def at(seq: list[Any], i: int) -> dict[str, Any] | None:
            return seq[i] if i < len(seq) and isinstance(seq[i], dict) else None

        # EM channels take precedence over plain meters for the same index.
        for i, em in enumerate(emeters):
            if isinstance(em, dict):
                out.channels[f"switch:{i}"] = Normalizer.gen1_emeter_channel(
                    at(relays, i), em, device_temp_c=out.device_temp_c
                )
        for i in range(max(len(relays), len(meters))):
            if f"switch:{i}" in out.channels:
                continue
            out.channels[f"switch:{i}"] = Normalizer.gen1_channel(
                at(relays, i), at(meters, i),
                device_temp_c=out.device_temp_c, meter_total_is_wh=meter_total_is_wh,
            )
        for i, light in enumerate(lights):
            if isinstance(light, dict):
                out.lights[f"light:{i}"] = Normalizer.gen1_light(
                    light, at(meters, i), meter_total_is_wh=meter_total_is_wh
                )
        for i, roller in enumerate(rollers):
            if isinstance(roller, dict):
                out.covers[f"cover:{i}"] = Normalizer.gen1_roller(roller)
        return out
