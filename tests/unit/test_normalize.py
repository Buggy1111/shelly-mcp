"""Unit tests for the Normalizer — Gen1↔Gen2 fixtures mirroring real device dumps.

The contract these lock down (a one-way door, ADR-003):
* Gen2 ``aenergy.total`` and Gen1 ``emeters[].total`` are **Wh** (pass through).
* Gen1 ``meters[].total`` is **Watt-minutes** → Wh by ÷60.
* A field the device can't report is ``None``, never a fake 0.
"""

from __future__ import annotations

from shelly_mcp.models import Generation
from shelly_mcp.normalize import Normalizer

# --- Real-shaped fixtures (trimmed from Michal's devices, see [[shelly-devices]]) ---
GEN2_SWITCH = {  # Plus Plug S — switch:0
    "id": 0, "output": True, "apower": 0.6, "voltage": 220.4, "current": 0.04,
    "freq": 50.0, "pf": 0.0,
    "aenergy": {"total": 379998.094, "by_minute": [0, 0, 0], "minute_ts": 1700000000},
    "ret_aenergy": {"total": 0.0},
    "temperature": {"tC": 44.6, "tF": 112.3},
    "source": "http",
}
GEN1_RELAY = {"ison": False, "source": "cloud", "overpower": False}
GEN1_METER = {"power": 0.0, "total": 548723, "is_valid": True}  # total is Watt-minutes


# ---------------------------------------------------------------- channels
def test_gen2_channel_energy_is_wh_passthrough() -> None:
    ch = Normalizer.gen2_channel(GEN2_SWITCH)
    assert ch.output is True
    assert ch.power_w == 0.6
    assert ch.voltage == 220.4
    assert ch.current == 0.04
    assert ch.energy_total_wh == 379998.094  # Wh, unchanged
    assert ch.ret_energy_total_wh == 0.0
    assert ch.temperature_c == 44.6
    assert ch.source == "http"
    assert ch.raw == GEN2_SWITCH  # raw payload preserved for power users (Pydantic copies it)


def test_gen1_channel_total_watt_minutes_to_wh() -> None:
    ch = Normalizer.gen1_channel(GEN1_RELAY, GEN1_METER)
    assert ch.output is False
    assert ch.power_w == 0.0
    # 548723 Wmin / 60 == 9145.38... Wh — the conversion that must never leak elsewhere
    assert ch.energy_total_wh is not None
    assert abs(ch.energy_total_wh - 548723 / 60.0) < 1e-9
    assert ch.source == "cloud"


def test_gen1_plain_meter_has_no_voltage_current() -> None:
    # None ≠ 0: a Gen1 plug genuinely cannot report voltage/current.
    ch = Normalizer.gen1_channel(GEN1_RELAY, GEN1_METER)
    assert ch.voltage is None
    assert ch.current is None


def test_gen1_emeter_total_is_already_wh() -> None:
    em = {"power": 1200.0, "total": 5000.0, "voltage": 231.0, "current": 5.2, "pf": 0.98}
    ch = Normalizer.gen1_emeter_channel(GEN1_RELAY, em)
    assert ch.energy_total_wh == 5000.0  # NOT divided by 60
    assert ch.voltage == 231.0
    assert ch.current == 5.2
    assert ch.pf == 0.98


def test_channel_missing_fields_stay_none_not_zero() -> None:
    ch = Normalizer.gen2_channel({"output": True})
    assert ch.power_w is None
    assert ch.energy_total_wh is None
    assert ch.temperature_c is None


def test_gen1_channel_carries_device_temp() -> None:
    ch = Normalizer.gen1_channel(GEN1_RELAY, GEN1_METER, device_temp_c=51.2)
    assert ch.temperature_c == 51.2


# ------------------------------------------------------------------ lights
def test_gen2_rgbw_light() -> None:
    raw = {"output": True, "brightness": 80, "rgb": [255, 23, 47], "white": 0, "apower": 7.3,
           "aenergy": {"total": 120.5}}
    lt = Normalizer.gen2_light(raw)
    assert lt.output is True
    assert lt.brightness == 80
    assert lt.rgb == (255, 23, 47)
    assert lt.white == 0
    assert lt.power_w == 7.3
    assert lt.energy_total_wh == 120.5


def test_gen2_cct_light_reports_ct_as_kelvin() -> None:
    lt = Normalizer.gen2_light({"output": True, "brightness": 70, "ct": 4000})
    assert lt.temp_k == 4000
    assert lt.rgb is None


def test_gen1_light_color_mode_uses_gain_as_brightness() -> None:
    raw = {"ison": True, "mode": "color", "red": 255, "green": 0, "blue": 0,
           "white": 0, "gain": 40, "brightness": 100, "temp": 4750}
    lt = Normalizer.gen1_light(raw)
    assert lt.output is True
    assert lt.brightness == 40       # gain, not the (ignored) white-mode brightness
    assert lt.rgb == (255, 0, 0)
    assert lt.temp_k is None          # colour mode → no white temp


def test_gen1_light_white_mode_uses_brightness_and_temp() -> None:
    raw = {"ison": True, "mode": "white", "brightness": 60, "temp": 3200, "gain": 100}
    lt = Normalizer.gen1_light(raw)
    assert lt.brightness == 60
    assert lt.temp_k == 3200
    assert lt.rgb is None


def test_gen1_dimmer_light_power_from_meter() -> None:
    raw = {"ison": True, "mode": "white", "brightness": 50}
    meter = {"power": 12.0, "total": 6000}  # Wmin
    lt = Normalizer.gen1_light(raw, meter)
    assert lt.power_w == 12.0
    assert lt.energy_total_wh == 100.0  # 6000 / 60


# ------------------------------------------------------------------ covers
def test_gen2_cover_state_is_canonical() -> None:
    cv = Normalizer.gen2_cover({"state": "opening", "current_pos": 40, "target_pos": 100,
                                "apower": 85.0})
    assert cv.state == "opening"
    assert cv.current_pos == 40
    assert cv.target_pos == 100
    assert cv.power_w == 85.0


def test_gen1_roller_motion_words_map_to_canonical() -> None:
    assert Normalizer.gen1_roller({"state": "stop", "current_pos": 50}).state == "stopped"
    assert Normalizer.gen1_roller({"state": "open"}).state == "opening"
    assert Normalizer.gen1_roller({"state": "close"}).state == "closing"


# -------------------------------------------------------- whole-status fan
def test_normalize_status_gen2_routes_components() -> None:
    status = {
        "switch:0": GEN2_SWITCH,
        "light:0": {"output": False, "brightness": 10},
        "cover:0": {"state": "stopped", "current_pos": 0},
        "input:0": {"state": False},   # not a controllable channel — ignored
        "wifi": {"sta_ip": "192.168.1.50"},
        "sys": {"uptime": 1234},
    }
    ns = Normalizer.normalize_status(status, Generation.GEN2)
    assert set(ns.channels) == {"switch:0"}
    assert set(ns.lights) == {"light:0"}
    assert set(ns.covers) == {"cover:0"}
    assert ns.channels["switch:0"].energy_total_wh == 379998.094


def test_normalize_status_gen1_joins_relays_and_meters() -> None:
    status = {
        "relays": [GEN1_RELAY, {"ison": True, "source": "http"}],
        "meters": [GEN1_METER, {"power": 5.0, "total": 120}],
        "tmp": {"tC": 38.5, "tF": 101.3},
    }
    ns = Normalizer.normalize_status(status, Generation.GEN1)
    assert set(ns.channels) == {"switch:0", "switch:1"}
    assert ns.device_temp_c == 38.5
    assert ns.channels["switch:0"].temperature_c == 38.5  # device temp on each channel
    assert ns.channels["switch:1"].output is True
    assert ns.channels["switch:1"].power_w == 5.0


def test_normalize_status_gen1_emeters_take_precedence() -> None:
    status = {
        "relays": [GEN1_RELAY],
        "meters": [GEN1_METER],
        "emeters": [{"power": 900.0, "total": 4200.0, "voltage": 230.0}],
    }
    ns = Normalizer.normalize_status(status, Generation.GEN1)
    ch = ns.channels["switch:0"]
    assert ch.energy_total_wh == 4200.0  # emeter Wh wins over meter Wmin
    assert ch.voltage == 230.0


def test_normalize_status_gen1_rollers_become_covers() -> None:
    status = {"rollers": [{"state": "stop", "current_pos": 70, "power": 0.0}]}
    ns = Normalizer.normalize_status(status, Generation.GEN1)
    assert ns.covers["cover:0"].state == "stopped"
    assert ns.covers["cover:0"].current_pos == 70
