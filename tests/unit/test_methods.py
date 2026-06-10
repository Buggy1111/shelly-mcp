"""Unit tests for method classification + Gen1 REST mapping (the rpc security spine)."""

from __future__ import annotations

import pytest

from shelly_mcp.backends.base import UnsupportedOnGeneration
from shelly_mcp.methods import (
    Classification,
    automation_allowed,
    classify,
    gen1_rest_for,
    is_read,
    requires_data_loss_ack,
)


@pytest.mark.parametrize("method", [
    "Shelly.GetStatus", "Switch.GetConfig", "Schedule.List", "Wifi.Scan",
    "Voltmeter.CheckExpression", "EM.GetCTTypes", "BLE.ListPairedDevices",
])
def test_reads_are_read(method: str) -> None:
    assert classify(method) is Classification.READ
    assert is_read(method) is True


@pytest.mark.parametrize("method", [
    "Switch.Set", "Switch.Toggle", "Light.Set", "Cover.Open", "Sys.SetConfig",
    "Schedule.Create", "Schedule.Delete", "Cloud.SetConfig", "PM1.ResetCounters",
])
def test_mutations_are_write(method: str) -> None:
    assert classify(method) is Classification.WRITE
    assert requires_data_loss_ack(method) is False


@pytest.mark.parametrize("method", [
    "Switch.Set", "Switch.Toggle", "Light.Set", "RGB.Set", "RGBW.Set", "CCT.Set",
    "Cover.Open", "Cover.Close", "Cover.GoToPosition",
])
def test_control_methods_are_automation_allowed(method: str) -> None:
    assert automation_allowed(method) is True


@pytest.mark.parametrize("method", [
    # WRITE by classification, but stored automation running them would bypass the
    # confirm gates their dedicated tools enforce — the allowlist must reject them.
    "Script.Eval", "Script.PutCode", "Script.Create", "Shelly.SetAuth",
    "Webhook.Create", "Schedule.Create", "Sys.SetConfig", "Shelly.Update", "KVS.Set",
    # destructive and read methods are never automation material
    "Shelly.FactoryReset", "Schedule.DeleteAll", "Switch.GetStatus",
    # prefix must match a whole component, not a lookalike
    "Switchboard.Set", "CoverArt.Set",
])
def test_gate_bypass_methods_are_not_automation_allowed(method: str) -> None:
    assert automation_allowed(method) is False


@pytest.mark.parametrize("method", [
    "Shelly.FactoryReset", "Shelly.ResetWiFiConfig", "Matter.FactoryReset",
    "Schedule.DeleteAll", "Webhook.DeleteAll", "EM1Data.DeleteAllData",
    "EM1.RevertToFactoryCalibration",
])
def test_destructive_methods_double_gate(method: str) -> None:
    assert classify(method) is Classification.DESTRUCTIVE
    assert requires_data_loss_ack(method) is True


def test_unknown_method_defaults_to_write_failsafe() -> None:
    # The critical fail-safe: a method we don't recognise is NEVER treated as a read.
    assert classify("FutureComponent.DoSomething") is Classification.WRITE
    assert is_read("FutureComponent.DoSomething") is False


def test_unknown_get_prefixed_method_is_read() -> None:
    assert classify("FutureComponent.GetWhatever") is Classification.READ


# --------------------------------------------------------------- Gen1 REST mapping
def test_gen1_switch_set_on_with_timer() -> None:
    path, query = gen1_rest_for("Switch.Set", {"id": 1, "on": True, "toggle_after": 30})
    assert path == "/relay/1"
    assert query == {"turn": "on", "timer": 30}


def test_gen1_switch_toggle() -> None:
    assert gen1_rest_for("Switch.Toggle", {"id": 0}) == ("/relay/0", {"turn": "toggle"})


def test_gen1_color_light_uses_color_path_and_gain() -> None:
    path, query = gen1_rest_for(
        "RGBW.Set", {"id": 0, "on": True, "rgb": [255, 10, 0], "brightness": 60, "white": 5}
    )
    assert path == "/color/0"
    assert query["turn"] == "on"
    assert (query["red"], query["green"], query["blue"]) == (255, 10, 0)
    assert query["gain"] == 60  # colour brightness -> gain
    assert query["white"] == 5


def test_gen1_white_dimmer_uses_light_path_and_brightness() -> None:
    path, query = gen1_rest_for(
        "Light.Set", {"id": 0, "on": True, "brightness": 40, "temp_k": 3000}
    )
    assert path == "/light/0"
    assert query["brightness"] == 40  # no rgb -> plain brightness
    assert query["temp"] == 3000


def test_gen1_cover_open_and_goto() -> None:
    assert gen1_rest_for("Cover.Open", {"id": 0}) == ("/roller/0", {"go": "open"})
    path, query = gen1_rest_for("Cover.GoToPosition", {"id": 0, "pos": 70})
    assert path == "/roller/0"
    assert query == {"go": "to_pos", "roller_pos": 70}


def test_gen1_status_and_config_paths() -> None:
    assert gen1_rest_for("Shelly.GetStatus")[0] == "/status"
    assert gen1_rest_for("Shelly.GetConfig")[0] == "/settings"


def test_gen1_unmappable_method_raises() -> None:
    with pytest.raises(UnsupportedOnGeneration, match="no Gen1 REST equivalent"):
        gen1_rest_for("Script.Create", {"id": 0})
