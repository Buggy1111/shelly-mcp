"""Canonical, generation-agnostic data models.

This is the **public contract** (ADR-003): the shapes that tools and the LLM see,
identical across Gen1 / Gen2+ / Cloud. A field is ``None`` when *this* device or
generation genuinely cannot report it — never a fake zero. The raw per-generation
payload is always kept under ``raw`` so power users are never blocked.

Changing these models is a one-way door — version deliberately if it must change.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

BackendKind = Literal["local_rpc", "local_rest", "cloud"]


class Generation(IntEnum):
    """Shelly hardware generation. Gen2/3/4 share the JSON-RPC component model."""

    GEN1 = 1  # ESP8266, HTTP REST (relays[]/meters[]/lights[]/rollers[])
    GEN2 = 2  # ESP32 "Shelly NG", JSON-RPC /rpc
    GEN3 = 3
    GEN4 = 4

    @property
    def is_rpc(self) -> bool:
        """True for the Gen2+ JSON-RPC family (everything except Gen1)."""
        return self is not Generation.GEN1


class DeviceIdentity(BaseModel):
    """Stable identity of a device, resolved once via ``GET /shelly`` and cached."""

    id: str = Field(description="Device id (lowercase, no colons), e.g. 'shellyplus1-abc'")
    name: str | None = Field(default=None, description="User-friendly name from config")
    location: str | None = Field(default=None, description="Room/area from config, e.g. 'kuchyň'")
    ip: str | None = Field(default=None, description="LAN IP, if known")
    gen: Generation
    model: str | None = Field(default=None, description="SKU code, e.g. 'SNPL-00112EU'")
    mac: str | None = None
    app: str | None = Field(default=None, description="Gen2+ app/profile string")
    fw: str | None = Field(default=None, description="Firmware version")
    online: bool = True
    auth_needed: bool = False
    backend: BackendKind | None = None


class Capabilities(BaseModel):
    """What a *specific* device/backend can actually do — never let a tool lie.

    Computed at onboarding from ``Shelly.GetComponents`` / ``ListMethods`` (Gen2+)
    or the ``/shelly`` capability fields (Gen1).
    """

    can_automate: bool = Field(
        default=False,
        description="Schedules/scripts/webhooks/KVS — local-only; always False on cloud",
    )
    has_energy: bool = False
    has_voltage_current: bool = Field(
        default=False, description="False on Gen1 plugs/relays — they report power only"
    )
    components: list[str] = Field(default_factory=list, description="e.g. ['switch:0', 'input:0']")
    methods: list[str] = Field(default_factory=list, description="Gen2+ RPC methods (ACL-filtered)")


class ChannelState(BaseModel):
    """Normalized state of one relay/switch channel (Gen1 relays[]/meters[] <-> Gen2 switch:0)."""

    output: bool | None = None
    power_w: float | None = None
    energy_total_wh: float | None = None
    ret_energy_total_wh: float | None = None
    voltage: float | None = None
    current: float | None = None
    pf: float | None = None
    freq: float | None = None
    temperature_c: float | None = None
    source: str | None = Field(
        default=None, description="What last changed it: http/button/timer/..."
    )
    raw: dict[str, Any] = Field(default_factory=dict)


class LightState(BaseModel):
    """Normalized state of a light/dimmer/RGB(W)/CCT channel."""

    output: bool | None = None
    brightness: int | None = Field(default=None, ge=0, le=100)
    rgb: tuple[int, int, int] | None = None
    white: int | None = None
    temp_k: int | None = Field(default=None, description="White colour temperature in Kelvin")
    power_w: float | None = None
    energy_total_wh: float | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class CoverState(BaseModel):
    """Normalized state of a roller/cover channel."""

    state: str | None = Field(default=None, description="open/closed/opening/closing/stopped")
    current_pos: int | None = Field(default=None, ge=0, le=100)
    target_pos: int | None = Field(default=None, ge=0, le=100)
    power_w: float | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class ComponentInfo(BaseModel):
    """One component present on a device, with the methods it supports."""

    key: str = Field(description="component:id, e.g. 'switch:0'")
    type: str = Field(description="component type, e.g. 'switch'")
    methods: list[str] = Field(default_factory=list)
