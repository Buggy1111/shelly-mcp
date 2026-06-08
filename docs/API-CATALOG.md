I now have comprehensive data from all the major sources. Let me compile the complete, authoritative reference document.

---

# Shelly MCP Server — Complete API Reference

**Sources consulted:**
- Gen2+ API: https://shelly-api-docs.shelly.cloud/gen2/
- Gen1 API: https://shelly-api-docs.shelly.cloud/gen1/
- BTHome spec: https://bthome.io/format/
- BLU TRV docs: https://shelly-api-docs.shelly.cloud/docs-ble/Devices/BLU_ZB/trv/
- Gen2 RPC Protocol: https://shelly-api-docs.shelly.cloud/gen2/General/RPCProtocol/
- Gen2 Common Errors: https://shelly-api-docs.shelly.cloud/gen2/General/CommonErrors/
- Gen2 Auth: https://shelly-api-docs.shelly.cloud/gen2/General/Authentication/
- Gen2 Notifications: https://shelly-api-docs.shelly.cloud/gen2/General/Notifications/
- Gen2 RPC Channels: https://shelly-api-docs.shelly.cloud/gen2/General/RPCChannels/

---

## SECTION 1 — `Shelly` System Namespace

All methods are called as `Shelly.<MethodName>` over any RPC channel.

### `Shelly.GetDeviceInfo`
Returns device identification and firmware info.

| Param | Type | Notes |
|-------|------|-------|
| `ident` | boolean, optional | Include extra fields (key, batch, fw_sbits) |

**Returns:** `id` (string), `mac` (string), `model` (string), `gen` (number), `fw_id` (string), `ver` (string), `app` (string), `profile` (string, optional), `auth_en` (boolean), `auth_domain` (string|null), `discoverable` (boolean, optional), `provision` (string), `key` (string, when ident=true), `batch` (string, when ident=true), `fw_sbits` (string, when ident=true)

---

### `Shelly.GetStatus`
Returns the status of ALL components. No parameters. Returns a merged object of every component status keyed by `type:id`.

---

### `Shelly.GetConfig`
Returns the configuration of ALL components. No parameters. Returns a merged object of every component config.

---

### `Shelly.GetComponents`
Retrieves components with optional filtering and pagination.

| Param | Type | Notes |
|-------|------|-------|
| `offset` | number, optional | Starting index |
| `include` | array of strings, optional | `"status"` and/or `"config"` |
| `keys` | array of strings, optional | Filter by component keys (format: `type:cid`) |
| `dynamic_only` | boolean, optional | Only dynamic/virtual components (default: false) |

**Returns:** `components` array (each with `key`, optional `status`, optional `config`), `cfg_rev` (number), `offset` (number), `total` (number)

---

### `Shelly.ListMethods`
Lists all available RPC methods respecting ACL and auth. No parameters.

**Returns:** `methods` (array of strings)

---

### `Shelly.ListProfiles`
Lists available device profiles (multi-profile devices only, e.g. Plus2PM in switch vs. cover mode). No parameters.

**Returns:** `profiles` (object mapping profile names to component arrays with type and count)

---

### `Shelly.SetProfile`
Activates a device profile. Triggers reboot; deletes all webhooks and schedules.

| Param | Type | Notes |
|-------|------|-------|
| `name` | string, required | Profile name |

**Returns:** `profile_was` (string — previous profile)

---

### `Shelly.ListTimezones`
Paginated list of available timezone names.

| Param | Type | Notes |
|-------|------|-------|
| `offset` | number, optional | Starting index |

**Returns:** `timezones` (array of strings), `offset` (number), `total` (number)

---

### `Shelly.DetectLocation`
Auto-detects device location and timezone via IP geolocation. No parameters.

**Returns:** `tz` (string|null), `lat` (number|null), `lon` (number|null)

---

### `Shelly.CheckForUpdate`
Checks available firmware updates. No parameters.

**Returns:** `stable` (object with `version`, `build_id`, optional), `beta` (object with `version`, `build_id`, optional)

---

### `Shelly.Update`
Initiates firmware update.

| Param | Type | Notes |
|-------|------|-------|
| `stage` | string, optional | `"stable"` or `"beta"` |
| `url` | string, optional | Custom firmware URL |

**Returns:** `null`

---

### `Shelly.Reboot`
Restarts the device.

| Param | Type | Notes |
|-------|------|-------|
| `delay_ms` | number, optional | Delay before reboot (min 500 ms, default 1000 ms) |

**Returns:** `null`

---

### `Shelly.FactoryReset`
Resets all config to defaults. No parameters. **Returns:** `null`

---

### `Shelly.ResetWiFiConfig`
Clears WiFi configuration. No parameters. **Returns:** `null`

---

### `Shelly.SetAuth`
Configures device authentication.

| Param | Type | Notes |
|-------|------|-------|
| `user` | string, required | Must be `"admin"` |
| `realm` | string, required | Device ID |
| `ha1` | string|null, required | `SHA256("admin:realm:password")` or `null` to disable |

**Returns:** `null`

---

### `Shelly.PutUserCA`
Uploads custom CA bundle in chunks (PEM format).

| Param | Type | Notes |
|-------|------|-------|
| `data` | string|null, required | PEM content or `null` to delete |
| `append` | boolean, optional | Continue multi-chunk upload (default: false) |

**Returns:** `len` (number — bytes stored)

---

### `Shelly.PutTLSClientCert`
Uploads TLS client certificate (`client.crt`) in chunks. Same params as `PutUserCA`. **Returns:** `len`

### `Shelly.PutTLSClientKey`
Uploads TLS client private key (`client.key`) in chunks. Same params. **Returns:** `len`

### `Shelly.PutHTTPServerCert`
Uploads HTTPS server certificate. Same params. Removing deletes key and CA bundle too. **Returns:** `len`

### `Shelly.PutHTTPServerKey`
Uploads HTTPS server private key. Same params. Removing also deletes cert and CA bundle. **Returns:** `len`

### `Shelly.PutHTTPServerCABundle`
Uploads CA bundle for verifying HTTPS clients. Same params. **Returns:** `len`

---

## SECTION 2 — Functional Components

Every functional component follows the pattern:
- `<Component>.GetStatus` — `id` (number, required) → status object
- `<Component>.GetConfig` — `id` (number, required) → config object
- `<Component>.SetConfig` — `id` (number, required), `config` (object, required) → `{restart_required?: boolean}`

Only additional/control methods are listed in full below.

---

### 2.1 Switch

**Gen1 compat endpoint:** `GET/POST /relay/<id>?turn=on|off|toggle&timer=<s>`
**Gen1 response:** `ison`, `has_timer`, `timer_started_at`, `timer_duration`, `timer_remaining`, `overpower`, `source`

**Methods:**

| Method | Key Params | Returns |
|--------|-----------|---------|
| `Switch.Set` | `id`\*, `on`\* (bool), `toggle_after` (s), `tag` (≤20 chars) | `was_on` (bool) |
| `Switch.Toggle` | `id`\*, `tag` | `was_on` (bool) |
| `Switch.ResetCounters` | `id`\*, `type` (array of counter names, optional) | previous counter values |

**Config fields:** `id`, `name`, `in_mode` (momentary/follow/flip/detached/cycle/activate), `in_locked` (bool), `initial_state` (off/on/restore_last/match_input), `auto_on` (bool), `auto_on_delay` (s), `auto_off` (bool), `auto_off_delay` (s), `autorecover_voltage_errors` (bool), `input_id` (0 or 1), `power_limit` (W), `voltage_limit` (V), `undervoltage_limit` (V), `current_limit` (A), `reverse` (bool), `counts.enable` (bool), `counts.power_thr` (W, default 100)

**Status fields:** `id`, `source`, `tag`, `output` (bool), `timer_started_at`, `timer_duration`, `apower` (W), `voltage` (V), `current` (A), `pf`, `freq` (Hz), `aenergy.total` (Wh), `aenergy.by_minute` (array, mWh), `aenergy.minute_ts`, `ret_aenergy.total`, `ret_aenergy.by_minute`, `ret_aenergy.minute_ts`, `counts.on_time`, `counts.on_time_rst_ts`, `counts.switch_on`, `counts.switch_on_rst_ts`, `counts.on_above_thr`, `counts.on_above_thr_rst_ts`, `temperature.tC`, `temperature.tF`, `errors` (array: overtemp/overpower/overvoltage/undervoltage)

**Webhook events:** `switch.on`, `switch.off`

**Devices:** Shelly1, 1PM, 1L, 2, 2.5, Plug/PlugS, 4Pro (Gen1); ShellyPlus1, Plus1PM, Plus2PM (switch profile), Pro2PM, Pro4PM, 1 Gen3, 1PM Gen3, 1 Gen4, 1PM Gen4, and most relay-type Gen2/Gen3/Gen4 devices

---

### 2.2 Cover (Roller Blind / Shutter)

**Gen1 compat endpoint:** `GET/POST /roller/<id>?go=open|close|stop|to_pos&roller_pos=<0-100>`

**Methods:**

| Method | Key Params | Returns |
|--------|-----------|---------|
| `Cover.Open` | `id`\*, `duration` (0.1–maxtime_open s), `tag` | null |
| `Cover.Close` | `id`\*, `duration` (0.1–maxtime_close s), `tag` | null |
| `Cover.Stop` | `id`\*, `tag` | null |
| `Cover.GoToPosition` | `id`\*, `pos` (0–100%) OR `rel` (−100..100%), `slat_pos`, `slat_rel`, `tag` | null |
| `Cover.Calibrate` | `id`\* | null |
| `Cover.ResetCounters` | `id`\*, `type` (optional array) | previous counters |

**Config fields:** `id`, `name`, `in_mode` (single/dual/detached), `in_locked`, `initial_state` (open/closed/stopped), `power_limit`, `voltage_limit`, `undervoltage_limit`, `current_limit`, `motor.idle_power_thr` (0–50 W), `motor.idle_confirm_period` (0.25–2 s), `maxtime_open` (0.1–300 s), `maxtime_close` (0.1–300 s), `swap_inputs`, `invert_directions`, `maintenance_mode`, `obstruction_detection.enable`, `obstruction_detection.direction` (open/close/both), `obstruction_detection.action` (stop/reverse), `obstruction_detection.power_thr`, `obstruction_detection.holdoff`, `safety_switch.enable`, `safety_switch.direction`, `safety_switch.action` (stop/reverse/pause), `safety_switch.allowed_move` (null/"reverse"), `slat.enable`, `slat.open_time` (0.5–30 s), `slat.close_time`, `slat.step` (1–100%), `slat.retain_pos`, `slat.precise_ctl`

**Status fields:** `id`, `source`, `tag`, `state` (open/closed/opening/closing/stopped/calibrating), `apower`, `voltage`, `current`, `pf`, `freq`, `aenergy`, `current_pos` (0–100 or null), `target_pos` (null during movement), `move_timeout`, `move_started_at`, `pos_control` (bool — calibrated), `last_direction` (open/close/null), `temperature.tC/tF`, `slat_pos` (0–100 or null), `errors`

**Errors:** overtemp, overpower, overvoltage, undervoltage, overcurrent, obstruction, safety_switch, calibration abort variants (timeout_open, timeout_close, bad_feedback, etc.)

**Devices:** Shelly2.5 (roller mode, Gen1); ShellyPlus2PM (cover profile), Pro2PM, ProDualCoverPM, 2PM Gen3, Shutter

---

### 2.3 Light (Dimmable White)

**Gen1 compat endpoint:** `GET/POST /light/<id>?turn=on|off|toggle&brightness=<0-100>&timer=<s>&transition=<ms>`

**Methods:**

| Method | Key Params | Returns |
|--------|-----------|---------|
| `Light.Set` | `id`\*, `on` (bool), `brightness` (%), `transition_duration` (s), `toggle_after` (s), `offset` (−100..100), `tag` | null |
| `Light.Toggle` | `id`\*, `tag` | null |
| `Light.DimUp` | `id`\*, `fade_rate` (1–5) | null |
| `Light.DimDown` | `id`\*, `fade_rate` (1–5) | null |
| `Light.DimStop` | `id`\* | null |
| `Light.SetAll` | `on`, `brightness`, `transition_duration`, `toggle_after`, `offset` | null |
| `Light.Calibrate` | `id`\* | null |
| `Light.ResetCounters` | `id`\*, `type` (optional array) | aenergy object |

**Config fields:** `id`, `name`, `in_mode` (follow/flip/activate/detached/dim/dual_dim), `op_mode`, `initial_state` (off/on/restore_last/toggle), `auto_on`, `auto_on_delay`, `auto_off`, `auto_off_delay`, `transition_duration`, `gamma` (0.4–4.0), `min_brightness_on_toggle`, `night_mode.enable`, `night_mode.brightness` (default 50), `night_mode.active_between` ([start,end] in HH:MM), `button_fade_rate` (1–5), `button_presets.button_doublepush.brightness`, `range_map` ([min,max] or null), `power_limit`, `voltage_limit`, `undervoltage_limit`, `current_limit`, `warmup.enable`, `warmup.brightness` (10–100%), `warmup.time_ms` (20–1000)

**Status fields:** `id`, `source`, `tag`, `output`, `brightness`, `timer_started_at`, `timer_duration`, `transition.target.output`, `transition.target.brightness`, `transition.started_at`, `transition.duration`, `temperature.tC/tF`, `aenergy`, `apower`, `voltage`, `current`, `calibration.progress`, `calibration.errors`, `calibration.flags` (no_load, uncalibrated)

**Webhook events:** `light.on`, `light.off`

**Devices:** Shelly Dimmer 1/2 (Gen1 via /light/0); ShellyDimmer Gen3/Gen4, ShellyPlus Dimmer 0/1-10V PM, and all Gen2+ dimmable white devices

---

### 2.4 RGB (RGB Color Control)

**Methods:** `RGB.GetStatus`, `RGB.GetConfig`, `RGB.SetConfig`, `RGB.Set`, `RGB.Toggle`, `RGB.DimUp`, `RGB.DimDown`, `RGB.DimStop`

**RGB.Set params:** `id`\*, `on` (bool), `brightness` (1–100%), `rgb` ([r,g,b] 0–255), `transition_duration` (s), `toggle_after` (s), `tag`

**Config fields:** `id`, `name`, `in_mode` (follow/flip/activate/detached/dim), `initial_state`, `auto_on/off/delay`, `transition_duration`, `min_brightness_on_toggle`, `night_mode.enable/brightness/rgb/active_between`, `button_fade_rate`, `button_presets.button_doublepush` (brightness, rgb), `current_limit`, `power_limit`, `voltage_limit`

**Status fields:** `id`, `source`, `tag`, `output`, `rgb` ([r,g,b]), `brightness`, `timer_started_at`, `timer_duration`, `transition` (target.output/rgb/brightness, started_at, duration), `temperature.tC/tF`, `aenergy`, `apower`, `voltage`, `current`, `errors`

**Devices:** ShellyPlus RGBW PM (RGB mode), Gen2/Gen3 RGB-capable devices

---

### 2.5 RGBW (RGBW Color Control)

**Methods:** Same as RGB plus white channel.

**RGBW.Set additional params:** `white` (0–255), `offset_white` (−100..100)

**Config/Status:** Identical to RGB plus `white` (0–255) and `night_mode.white`, `button_presets.button_doublepush.white`

**Devices:** ShellyRGBW2 (Gen1 via /color/0), ShellyPlus RGBW PM (RGBW mode)

---

### 2.6 CCT (Color Temperature Tunable White)

**Methods:** `CCT.GetStatus`, `CCT.GetConfig`, `CCT.SetConfig`, `CCT.Set`, `CCT.Toggle`, `CCT.DimUp`, `CCT.DimDown`, `CCT.DimStop`

**CCT.Set params:** `id`\*, `on` (bool), `brightness` (%), `ct` (Kelvin), `transition_duration` (s), `toggle_after` (s), `tag`

**Config fields:** `id`, `name`, `initial_state`, `auto_on/off/delay`, `transition_duration`, `min_brightness_on_toggle`, `night_mode.enable/brightness/ct/active_between`, `button_fade_rate`, `button_presets.button_doublepush` (brightness, ct), `range_map` (output range, or null), `ct_range` ([min_K, max_K] or null), `current_limit`, `power_limit`, `voltage_limit`

**Status fields:** `id`, `source`, `tag`, `output`, `brightness`, `ct` (K), `timer_started_at`, `timer_duration`, `transition` (target.output/brightness/ct, started_at, duration), `temperature.tC/tF`, `apower`, `voltage`, `current`, `errors`

**Devices:** Shelly Duo (Gen1 via /light/0), ShellyPlus 0-10V Dimmer, CCT-capable bulbs

---

### 2.7 Input

**Methods:**

| Method | Key Params | Returns |
|--------|-----------|---------|
| `Input.GetStatus` | `id`\* | status |
| `Input.GetConfig` | `id`\* | config |
| `Input.SetConfig` | `id`\*, `config`\* | — |
| `Input.CheckExpression` | `expr`\* (string), `inputs`\* (array, ≤5) | `results` ([input,output] tuples) |
| `Input.ResetCounters` | `id`\*, `type` (optional array) | `counts.total` |
| `Input.Trigger` | `id`\*, `event_type`\* (btn_down/btn_up/single_push/double_push/triple_push/long_push) | null — PlusI4/I4 Gen3/I4 DC Gen3 only |

**Config fields:** `id`, `name`, `type` (switch/button/analog/count), `enable`, `invert` (switch/button/analog), `factory_reset` (switch/button), `report_thr` (analog — V threshold), `range_map` (analog), `range` (analog), `xpercent.expr/unit` (analog), `count_rep_thr` (count), `freq_window` (count), `freq_rep_thr` (count), `xcounts.expr/unit` (count), `xfreq.expr/unit` (count)

**Status fields:** `id`, `state` (bool|null, switch/button), `percent` (analog), `xpercent` (analog), `counts.total/xtotal/by_minute/xby_minute/minute_ts` (count), `freq` (count), `xfreq` (count), `errors`

**Webhook events:**
- switch: `input.toggle_on`, `input.toggle_off`
- button: `input.button_push`, `input.button_longpush`, `input.button_doublepush`, `input.button_triplepush`
- analog: `input.analog_change` (attrs: percent, xpercent), `input.analog_measurement`
- count: `input.count_change` (attrs: total, xtotal), `input.count_measurement`, `input.freq_change` (attrs: freq, xfreq), `input.freq_measurement`

---

### 2.8 PM1 (Single-Channel Power Meter)

**Methods:** `PM1.GetStatus`, `PM1.GetConfig`, `PM1.SetConfig`, `PM1.ResetCounters` (`id`\*, `type` optional)

**Config fields:** `id`, `name`, `reverse` (bool — reverse active power direction), `alarms.voltage` ([under,over] thresholds or null), `alarms.current` ([under,over] or null), `alarms.power` ([under,over] or null)

**Status fields:** `id`, `voltage` (V), `current` (A), `apower` (W), `aprtpower` (VA), `pf`, `freq` (Hz), `aenergy.total/by_minute/minute_ts`, `ret_aenergy.total/by_minute/minute_ts`, `errors`, `flags` (undervoltage/overvoltage/undercurrent/overcurrent/underpower/overpower)

**Devices:** ShellyPlus1PM, ShellyPro1PM, ShellyPlug S Gen2+, and devices with integrated single-channel metering

---

### 2.9 EM (3-Phase Energy Meter)

**Methods:** `EM.GetStatus`, `EM.GetConfig`, `EM.SetConfig`, `EM.PhaseToPhaseCalib` (`id`\*, `from`\*, `to`\*), `EM.PhaseToPhaseCalibReset` (`id`\*, `phase`\*), `EM.GetCTTypes` (`id`\*)

**Config fields:** `id`, `name`, `blink_mode_selector` (active_energy/apparent_energy), `phase_selector` (a/b/c/all), `monitor_phase_sequence` (bool), `reverse.a/b/c` (bool — CT direction per phase), `ct_type` (string — e.g. "120A", "400A"), `alarms.voltage/current/power` (per-phase thresholds)

**Status fields (per phase A, B, C, neutral):** `a_current`, `a_voltage`, `a_act_power` (W), `a_aprt_power` (VA), `a_pf`, `a_freq` (Hz), `a_errors`, `a_flags` (and same for b_, c_, n_) — **Totals:** `total_current`, `total_act_power`, `total_aprt_power`, `user_calibrated_phase` (array), `errors` (phase_sequence, power_meter_failure, ct_type_not_set)

**Devices:** ShellyPro3EM, ShellyProEM

---

### 2.10 EM1 (Single-Phase Energy Meter)

**Methods:** `EM1.GetStatus`, `EM1.GetConfig`, `EM1.SetConfig`, `EM1.CalibrateFrom` (`id`\*, `other_id`\*), `EM1.RevertToFactoryCalibration` (`id`\*), `EM1.GetCTTypes` (`id`\*)

**Config fields:** `id`, `name`, `reverse` (bool), `ct_type` (string), `alarms.voltage/current/power`

**Status fields:** `id`, `voltage` (V|null), `current` (A|null), `act_power` (W|null), `aprt_power` (VA|null), `pf` (null), `freq` (Hz|null), `calibration` ("factory" or source EM1 id), `errors`, `flags`

**Devices:** Shelly EM Gen3 (2× EM1 instances), ShellyProEM

---

### 2.11 EMData (3-Phase Energy History)

**Methods:**

| Method | Key Params | Returns |
|--------|-----------|---------|
| `EMData.GetStatus` | `id`\* | per-phase total/returned energy (Wh), `errors` |
| `EMData.GetConfig` | `id`\* | `{}` (no config) |
| `EMData.SetConfig` | `id`\*, `config`\* | `restart_required` |
| `EMData.GetRecords` | `id`\*, `ts` (default 0) | `data_blocks` array (ts, period, records count) |
| `EMData.GetData` | `id`\*, `ts`\*, `end_ts` (optional), `add_keys` (bool, default true) | `keys`, `data` (ts/period/values), `next_record_ts` |
| `EMData.GetNetEnergies` | `id`\*, `ts`\*, `end_ts`, `period`\* (300/900/1800/3600 s), `add_keys` | `keys` (a/b/c_net_act_energy), `data`, `next_record_ts` |
| `EMData.DeleteAllData` | `id`\* | null |
| `EMData.ResetCounters` | `id`\* | null |

**EMData.GetStatus fields:** `id`, `a_total_act_energy`, `a_total_act_ret_energy`, `b_total_act_energy`, `b_total_act_ret_energy`, `c_total_act_energy`, `c_total_act_ret_energy`, `total_act`, `total_act_ret`, `errors`

---

### 2.12 EM1Data (Single-Phase Energy History)

**Methods:** Mirrors EMData but single-phase: `EM1Data.GetStatus`, `GetConfig`, `SetConfig`, `GetRecords`, `GetData`, `GetNetEnergies` (key: `net_act_energy`), `DeleteAllData`, `ResetCounters`

**EM1Data.GetStatus fields:** `id`, `total_act_energy` (Wh), `total_act_ret_energy` (Wh), `errors`

---

### 2.13 Temperature

**Methods:** `Temperature.GetStatus`, `Temperature.GetConfig`, `Temperature.SetConfig`

**Config:** `id`, `name` (≤64 chars), `report_thr_C` (default 0.5–5.0°C), `offset_C` (default ±50°C)

**Status:** `id`, `tC` (number|null), `tF` (number|null), `errors` (out_of_range, read)

**Webhook events:** `temperature.change` (attrs: tC, tF), `temperature.measurement` (60 s interval)

**Devices:** Any device with temperature sensor (built-in or via SensorAddon/DS18B20/DHT22); also internal temp on Switch/Light/Cover devices

---

### 2.14 Humidity

**Methods:** `Humidity.GetStatus`, `Humidity.GetConfig`, `Humidity.SetConfig`

**Config:** `id`, `name` (≤64 chars), `report_thr` (1.0–20.0%, default), `offset` (±50%)

**Status:** `id`, `rh` (number|null), `errors` (out_of_range, read)

**Webhook events:** `humidity.change` (attr: rh), `humidity.measurement` (60 s interval)

**Devices:** Shelly H&T (Gen1); ShellyHT Gen3, devices with DHT22 via SensorAddon

---

### 2.15 DevicePower

**Methods:** `DevicePower.GetStatus`, `DevicePower.GetConfig`, `DevicePower.SetConfig` (config object is empty — no configurable properties)

**Status:** `id`, `battery.V` (number|null — battery voltage), `battery.percent` (number|null), `external.present` (bool — external power connected), `errors`

**Note:** Battery-operated devices only.

**Devices:** Shelly H&T, Door/Window, Button1, Motion, and all battery-operated Gen2+ devices

---

### 2.16 Voltmeter

**Methods:** `Voltmeter.GetStatus`, `Voltmeter.GetConfig`, `Voltmeter.SetConfig`, `Voltmeter.CheckExpression` (`expr`\*, `inputs`\* array ≤5)

**Config:** `id`, `name` (≤64 chars), `report_thr` (V threshold), `range` (0 or 1 — device-specific), `xvoltage.expr` (JS expr using `x`, ≤100 chars), `xvoltage.unit` (≤20 chars)

**Status:** `id`, `voltage` (V|null), `xvoltage` (number|null — transformed), `errors` (out_of_range, read)

**Devices:** Shelly Uni (Gen1 analog in); devices with SensorAddon (voltmeter peripheral); ShellyPlus Addon-capable devices

---

### 2.17 Smoke

**Methods:** `Smoke.GetStatus`, `Smoke.GetConfig`, `Smoke.SetConfig`, `Smoke.Mute` (`id`\* — mutes alarm)

**Config:** `id`, `name` (≤64 chars)

**Status:** `id`, `alarm` (bool), `mute` (bool)

**Webhook events:** `smoke.alarm`, `smoke.alarm_off`, `smoke.alarm_test`

**Devices:** Shelly Smoke (Gen1); Shelly Smoke Gen2+

---

### 2.18 Illuminance

**Methods:** `Illuminance.GetStatus`, `Illuminance.GetConfig`, `Illuminance.SetConfig`

**Config:** `id`, `name` (≤64 chars), `dark_thr` (lux), `bright_thr` (lux)

**Status:** `id`, `lux` (number|null), `illumination` (string|null — "dark"/"twilight"/"bright"), `errors` (out_of_range, read)

**Webhook events:** `illuminance.change` (attrs: lux, illumination) — triggers when level category changes

**Devices:** Shelly Motion/Motion2, Door/Window 2, Shelly H&T Plus Gen3 (if equipped)

---

### 2.19 Thermostat / TRV (Thermostatic Radiator Valve)

**Note:** The Gen2 API documents this under the `Trv` namespace for the BLU TRV device specifically. There is no standalone "Thermostat" Gen2 functional component in the current docs — thermostat logic is handled via Sys schedule + Temperature + Switch, or via the BluTrv bridge component (see Section 5). The Gen1 Shelly TRV had its own HTTP API.

**BLU TRV direct methods** (on the TRV device itself, accessible via BluTrv.Call or when BLU TRV acts as host):

| Method | Description |
|--------|-------------|
| `Trv.GetConfig` | Get TRV config |
| `Trv.SetConfig` | Set TRV config (floor_heating, accel, auto_calibrate, anticlog, power_save, silent_mode flags) |
| `TRV.SetTarget` | Set target temperature (°C) |
| `TRV.SetFlag` / `TRV.ClearFlag` | Manage boolean flags |
| `TRV.GetStatus` | Get valve pos, stepper steps, current_C, target_C, schedule_rev, errors |
| `TRV.Calibrate` | Run stepper motor calibration (≤10 s) |
| `TRV.SetOverride` | Temporary target temperature + duration |
| `TRV.ClearOverride` | End override |
| `TRV.SetBoost` | Open valve to max for duration |
| `TRV.ClearBoost` | End boost mode |
| `TRV.SetExternalTemperature` | Feed external temp reading or switch to internal sensor |
| `TRV.SetPosition` | Manually set valve % (when thermostat disabled) |
| `Trv.AddScheduleRule` | Add cron-based schedule rule (max 10) |
| `Trv.UpdateScheduleRule` | Update schedule rule |
| `Trv.RemoveScheduleRule` | Delete schedule rule |
| `Trv.ListScheduleRules` | List all rules |
| `Trv.ShowMessage` | Display text on TRV screen (≤10 chars) |
| `Trv.PairingComplete` | Show YES/NO on TRV display |

**TRV Status fields:** `pos` (0–100%), `current_C`, `target_C`, `steps` (stepper counter), `schedule_rev`, `boost` (ts, duration), `override` (ts, duration), `errors` (not_calibrated, not_mounted, battery_low, ext_temp_missing)

---

## SECTION 3 — Automation & Scripting Services

### 3.1 Script

**Limits:** max 3 concurrent running scripts per device; max 10 script instances

| Method | Key Params | Returns |
|--------|-----------|---------|
| `Script.Create` | `name` (string, optional — defaults to `script_<id>`) | `id` (number) |
| `Script.Delete` | `id`\* | null |
| `Script.List` | — | `scripts` (array of {id, name, enable, running}) |
| `Script.PutCode` | `id`\*, `code`\* (string, len>0), `append` (bool, default false) | `len` (total bytes) |
| `Script.GetCode` | `id`\*, `offset` (default 0), `len` (default: to end) | `data` (string), `left` (bytes remaining) |
| `Script.Start` | `id`\* | `was_running` (bool) |
| `Script.Stop` | `id`\* | `was_running` (bool) |
| `Script.Eval` | `id`\*, `code`\* (len>0) | `result` (string) |
| `Script.SetConfig` | `id`\*, `config`\* ({name, enable}) | `restart_required` (bool) |
| `Script.GetConfig` | `id`\* | `{id, name, enable}` |
| `Script.GetStatus` | `id`\* | `{id, running, mem_used, mem_peak, mem_free, cpu (v1.7.0+), errors?}` |

---

### 3.2 Schedule

**Limits:** max 20 schedule jobs per device; max 5 calls per job; min 1 call per job

**Cron Timespec format:** 6 fields: `ss mm hh dd MM DOW`
- `ss` = seconds (0–59)
- `mm` = minutes (0–59)
- `hh` = hours (0–23)
- `dd` = day of month (1–31)
- `MM` = month (1–12)
- `DOW` = day of week (0=Sun … 6=Sat)
- Standard cron wildcards apply (`*`, `,`, `-`). Leading zeros NOT supported (use `8` not `08`).

**`calls[]` structure:** array of objects, each with:
- `method` (string, required) — any valid RPC method name
- `params` (object, optional) — method parameters

| Method | Key Params | Returns |
|--------|-----------|---------|
| `Schedule.Create` | `enable` (bool, default true), `timespec`\* (cron string), `calls`\* (array, 1–5 objects) | `id` (number), `rev` (number) |
| `Schedule.Update` | `id`\*, `enable`, `timespec`, `calls` | `rev` (number) |
| `Schedule.Delete` | `id`\* | `rev` (number) |
| `Schedule.DeleteAll` | — | `rev` (number) |
| `Schedule.List` | — | `jobs` (array of job objects), `rev` (number) |

---

### 3.3 Webhook

**Limits:** max 20 webhooks (10 on battery-operated devices); max 5 URLs per webhook; max 300 chars per URL

| Method | Key Params | Returns |
|--------|-----------|---------|
| `Webhook.Create` | `event`\*, `cid`\*, `enable` (bool, default false), `name`, `ssl_ca` (null/`*`/`user_ca.pem`), `urls`\* (1–5), `active_between` (["HH:MM","HH:MM"]), `condition` (JS expr string|null), `repeat_period` (s, 0=always, negative=once) | `id`, `rev` |
| `Webhook.Update` | `id`\*, any fields from Create | `rev` |
| `Webhook.Delete` | `id`\* | `rev` |
| `Webhook.DeleteAll` | — | `rev` |
| `Webhook.List` | — | `hooks` array, `rev` |
| `Webhook.ListSupported` | — | `types` object (deprecated v2.0.0) |
| `Webhook.ListAllSupported` | `offset` (optional) | `types` array, `offset`, `total` |

**Event taxonomy (non-exhaustive — use ListAllSupported for full list):**

| Event | Attributes |
|-------|-----------|
| `switch.on` / `switch.off` | — |
| `input.toggle_on` / `input.toggle_off` | — |
| `input.button_push` / `input.button_longpush` / `input.button_doublepush` / `input.button_triplepush` | — |
| `input.analog_change` / `input.analog_measurement` | `percent`, `xpercent` |
| `input.count_change` / `input.count_measurement` | `total`, `xtotal` |
| `input.freq_change` / `input.freq_measurement` | `freq`, `xfreq` |
| `light.on` / `light.off` | — |
| `temperature.change` / `temperature.measurement` | `tC`, `tF` |
| `humidity.change` / `humidity.measurement` | `rh` |
| `illuminance.change` | `lux`, `illumination` |
| `smoke.alarm` / `smoke.alarm_off` / `smoke.alarm_test` | — |
| `bthomesensor.value_change` | `value` |
| `em1.current_change` | `current` |
| `boolean.change` | — |

**Condition system:** JS expression evaluated with context: `config`, `status`, `info`, `ev`/`event` (event attributes). Example: `"event.tC > 20"`

**URL token replacement:** `${expr}` (URL-encoded) within URL strings. Escape literal: `$${`.

---

### 3.4 KVS (Key-Value Store)

**Limits:** max 50 keys; max key length 42 chars; max value length 253 chars

| Method | Key Params | Returns |
|--------|-----------|---------|
| `KVS.Set` | `key`\*, `value`\* (any JSON), `etag` (optional — atomic guard) | `etag` (string), `rev` (number) |
| `KVS.Get` | `key`\* | `etag`, `value` |
| `KVS.GetMany` | `match` (wildcard pattern, default `*`), `offset` | `items` (array), `offset`, `total` |
| `KVS.List` | `match` (wildcard pattern, default `*`) | `keys` (object mapping key→etag), `rev` |
| `KVS.Delete` | `key`\*, `etag` (optional — prevents deletion if value changed) | `rev` |

**Pattern wildcards for KVS.GetMany:** `*` (any non-`/` chars), `**` (any chars), `?` (single non-`/` char), `|` or `,` (alternatives)
**Pattern wildcards for KVS.List:** `*` (any non-`/` chars), `?` (single), `,` (alternatives)

---

### 3.5 Virtual Components

**Limits:** max 10 instances per device; ID range 200–299; Gen3 and Gen2 Pro devices only (v1.1.0+)

**Component types:** `Boolean`, `Number`, `Text`, `Enum`, `Group`, `Button`

**Universal methods:** `Virtual.Add` (`type`\*, `config` optional, `id` optional 200–299 → `{id}`), `Virtual.Delete` (`key`\* format `<type>:<cid>` → null)

Each type supports `<Type>.GetStatus`, `<Type>.GetConfig`, `<Type>.SetConfig`, `<Type>.Set`

**Boolean config:** `id`, `name`, `persisted` (bool), `default_value` (bool), `meta` (object|null — UI metadata)
**Boolean status:** `value` (bool), `source`, `last_update_ts`
**Webhook:** `boolean.change`

**Number config:** `id`, `name`, `persisted`, `default_value` (number), `min` (default −999999999999999), `max` (default +999999999999999), `meta`
**Number status:** `value` (number), `source`, `last_update_ts`

**Text config:** `id`, `name`, `persisted`, `default_value` (string), `meta`
**Text status:** `value` (string), `source`, `last_update_ts`

**Enum config:** `id`, `name`, `persisted`, `default_value` (any option or null), `options`\* (array — required, defines valid values), `meta`
**Enum status:** `value` (any option|null), `source`, `last_update_ts`

**Group config:** `id`, `name`, `meta`
**Group status:** `value` (array of component key strings, e.g. `["boolean:200","number:201"]`), `source`, `last_update_ts`

---

## SECTION 4 — Connectivity & System Components

### 4.1 Sys

**Methods:** `Sys.GetStatus`, `Sys.GetConfig`, `Sys.SetConfig`, `Sys.SetTime` (`unixtime`\* — Unix UTC with optional ms fraction)

**Config fields:**
- `device.name`, `device.eco_mode`, `device.mac` (read-only), `device.fw_id` (read-only), `device.profile`, `device.discoverable`, `device.addon_type` (string|null — set "sensor" or "LoRa" to enable addon), `device.sys_btn_toggle`, `device.tls_check_cert_validity_time`, `device.enhanced_security` (read-only on v2.0.0+)
- `location.tz`, `location.lat`, `location.lon`
- `debug.mqtt.enable`, `debug.websocket.enable`, `debug.udp.addr`, `debug.file_log.enable`
- `rpc_udp.dst_addr`, `rpc_udp.listen_port` (null to disable)
- `sntp.server`

**Status fields:** `mac`, `restart_required`, `time` (HH:MM|null), `unixtime` (|null), `last_sync_ts` (|null), `uptime`, `ram_size`, `ram_free`, `fs_size`, `fs_free`, `cfg_rev`, `kvs_rev`, `schedule_rev`, `webhook_rev`, `knx_rev` (if KNX), `btrelay_rev` (if BLE relay), `bthc_rev` (if BTHomeControl), `available_updates` (beta/stable), `wakeup_reason` (battery devices only), `wakeup_period`, `utc_offset`

---

### 4.2 WiFi

**Methods:** `Wifi.GetStatus`, `Wifi.GetConfig`, `Wifi.SetConfig`, `Wifi.Scan` (→ list of available networks), `Wifi.ListAPClients` (→ list of clients connected to AP)

**Config:**
- `ap.ssid`, `ap.pass` (write-only), `ap.is_open`, `ap.enable`, `ap.range_extender.enable`
- `sta.ssid`, `sta.pass` (write-only), `sta.is_open`, `sta.enable`, `sta.ipv4mode` (dhcp/static), `sta.ip`, `sta.netmask`, `sta.gw`, `sta.nameserver`
- `sta1` — identical to `sta`, serves as fallback
- `roam.rssi_thr` (default −80 dBm), `roam.interval` (s, default 60)

**Status:** `sta_ip` (|null), `status` (disconnected/connecting/connected/got_ip), `ssid` (|null), `bssid`, `channel`, `rssi`, `ap_client_count`

---

### 4.3 Eth (Ethernet)

**Methods:** `Eth.GetStatus`, `Eth.GetConfig`, `Eth.SetConfig`, `Eth.ListClients` (`offset` optional → DHCP clients with host/mac/ip/ttl)

**Config:** `enable`, `server_mode` (bool), `ipv4mode` (dhcp/static), `ip`, `netmask` (default 255.255.255.0), `gw`, `nameserver`, `dhcp_start`, `dhcp_end` (server mode)

**Status:** `ip` (|null)

**Devices:** ShellyProEM, Pro4PM, and all Pro-series/rack devices with Ethernet port

---

### 4.4 BLE (Bluetooth Low Energy)

**Methods:** `BLE.GetStatus`, `BLE.GetConfig`, `BLE.SetConfig`, `BLE.StartPairing` (enables bonding), `BLE.StopPairing`, `BLE.ListPairedDevices`, `BLE.DeletePairedDevice`, `BLE.AdvertiseOnce`, `BLE.CloudRelay.List` (→ MAC addresses), `BLE.CloudRelay.ListInfos` (`offset` optional), `BLE.StartAssociations` (generic BT device association, v2.0.0+), `BLE.StartBluTrvAssociations` (deprecated — use StartAssociations)

**Config:** `rpc.enable` (bool — BLE RPC service), `rpc.keep_running` (bool, v1.6.0+), `observer.enable` (bool — persistent BLE scanning, obsoleted v1.5.0)

**Status:** `addr` (BT MAC with type suffix), `flags` (array: "scanning"/"advertising"/"connected"), `pairing` (object with started_at/duration, when active), `blutrv_assoc` (when active)

---

### 4.5 Cloud

**Methods:** `Cloud.GetStatus`, `Cloud.GetConfig`, `Cloud.SetConfig` (→ `restart_required`)

**Config:** `enable` (bool), `server` (string|null)

**Status:** `connected` (bool)

---

### 4.6 MQTT

**Methods:** `MQTT.GetStatus`, `MQTT.GetConfig`, `MQTT.SetConfig`

**Config:** `enable`, `server` (host:port|null), `client_id` (|null — device ID default), `user` (|null), `ssl_ca` (null=plain/`*`=TLS unvalidated/`user_ca.pem`/`ca.pem`), `topic_prefix` (≤300 chars|null), `rpc_ntf` (bool, default true), `status_ntf` (bool, default false), `use_client_cert` (bool, default false), `enable_rpc` (bool), `enable_control` (bool, default true)

**Status:** `connected` (bool)

**MQTT topics:** requests to `<shelly-id>/rpc`; responses to `<src>/rpc`; notifications to `<shelly-id>/events/rpc`; online status on `<shelly-id>/online`

---

### 4.7 Ws (Outbound WebSocket)

**Methods:** `Ws.GetStatus`, `Ws.GetConfig`, `Ws.SetConfig`

**Config:** `enable` (bool), `server` (string — `wss://` prefix enables TLS), `ssl_ca` (`*`/`user_ca.pem`/`ca.pem`)

**Status:** `connected` (bool)

**Note:** Upon connection, device emits NotifyFullStatus. Supports all inbound WS and MQTT features.

---

### 4.8 Matter

**Methods:** `Matter.GetStatus`, `Matter.GetConfig`, `Matter.SetConfig`, `Matter.GetSetupCode` (→ `qr_code`, `manual_code`), `Matter.FactoryReset` (unpairs all fabrics)

**Config:** `enable` (bool)

**Status:** `num_fabrics` (number), `commissionable` (bool)

**Availability:** Gen3 and Gen4 devices only

---

### 4.9 Zigbee

**Methods:** `Zigbee.GetStatus`, `Zigbee.GetConfig`, `Zigbee.SetConfig`, `Zigbee.StartNetworkSteering` (no params/returns)

**Config:** `enable` (bool)

**Status:** `network_state` (disabled/initializing/steering/joined/failed)

**Availability:** Gen4 devices (expanded in changelog with inputs support and OTA)

---

### 4.10 Modbus

**Methods:** `Modbus.GetStatus`, `Modbus.GetConfig`, `Modbus.SetConfig`

**Config:** `enable` (bool — enables Modbus TCP server on port 502)

**Status:** `enabled` (bool)

**Modbus register categories:** EM/EMData/EM1/EM1Data/Switch/Input data registers; device info at 30000 (MAC), 30006 (model), 30016 (name)

**Devices:** ShellyProEM, ShellyPro3EM, Pro-series devices

---

### 4.11 KNX (Integration)

**Methods:** `Knx.GetStatus`, `Knx.GetConfig`, `Knx.SetConfig` (config/status details require direct page access — not exposed in current docs)

**Source:** https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Knx/ (404 — may be behind firmware version gate)

**Status:** `knx_rev` visible in Sys.GetStatus when supported

---

### 4.12 LNM (Local Network Messaging — Dynamic Component)

**Methods:** `LNM.GetConfig`, `LNM.SetConfig`, `LNM.GetStatus`, `LNM.Create` (ID 200–299), `LNM.Delete`

**Config:** `addr` (multicast ip:port, 224.0.0.0/4 range), `tx.enable`, `tx.components` (array of keys: switch/cover/input/light/pm1/em1/em), `rx.enable`

**Status:** `tx_msgs`, `rx_msgs`, `since` (timestamp)

**Events (scripts only):** `rx` — fires on incoming multicast with device ID, component status, metadata

---

### 4.13 SensorAddon (Shelly Plus Add-On)

**Enable:** Set `Sys.config.device.addon_type = "sensor"` then reboot.

**Methods:**

| Method | Params | Returns |
|--------|--------|---------|
| `SensorAddon.AddPeripheral` | `type`\* (ds18b20/dht22/digital_in/analog_in/voltmeter), `cid` (optional 100–199), `addr` (required for ds18b20) | component id |
| `SensorAddon.RemovePeripheral` | `type`\*, `cid`\* | null |
| `SensorAddon.UpdatePeripheral` | `type`\* (currently only ds18b20), `cid`\*, `addr`\* | null |
| `SensorAddon.GetPeripherals` | — | configured links (type, addr, component) |
| `SensorAddon.OneWireScan` | — | `devices` array (type/addr/component) — error if DHT22 in use |

**Peripheral → Component mapping:**
- `ds18b20` → Temperature (ID 100–199)
- `dht22` → Temperature + Humidity (IDs 100–199)
- `digital_in` → Input
- `analog_in` → Input (analog type)
- `voltmeter` → Voltmeter

**Devices:** ShellyPlus1PM, Plus2PM, and other Plus-series with addon port; Gen3 devices

---

### 4.14 LoRa Add-On

**Enable:** Set `Sys.config.device.addon_type = "LoRa"` then reboot.

**Methods:** `LoRa.GetConfig`, `LoRa.SetConfig`, `LoRa.GetStatus`, `LoRa.SendBytes` (`id`\*, `data`\* base64), `LoRa.Send` (`id`\*, `lr_addr`\* 8-hex, `tx_key` optional base64 16B, `tx_key_id` optional 1–3, `data`\* base64)

**Config:** `id`, `band_plan` (EU868/US915/BR915-928), `freq` (Hz), `bw` (125/250/500 kHz), `dr` (7–12), `cr` (5 or 8), `plen` (6–65535), `txp` (0–14 dBm), `rx_enable`, `fh.enable`, `fh.freqs` (64 entries for US915), `shelr.lr_addr`, `shelr.tx_key_id`, `shelr.key1/2/3`, `shelr.accept`

**Status:** `id`, `bytes_sent`, `bytes_recd`, `air_time_hr_ms`, `send_fails`, `fw_version`, `shelr.key1/2/3` (bool — presence), `available_updates`, `update.progress/state/ts`, `flags` (duty_cycle_limit, send_blocked, lp_mode), `errors` (limit_reached, addon_update_required, ota_update_failed)

**Devices:** Gen3/Gen4 devices with LoRa Add-On hardware

---

### 4.15 HTTP (Outbound HTTP from device)

**Methods:**

| Method | Key Params | Returns |
|--------|-----------|---------|
| `HTTP.GET` | `url`\*, `timeout`, `ssl_ca` (null/`user_ca.pem`/`*`) | `code`, `message`, `headers`, `body`, `body_b64` (max 16 KB binary) |
| `HTTP.POST` | `url`\*, `body`\* (or `body_b64`), `content_type` (default: application/json), `timeout`, `ssl_ca` | same as GET |
| `HTTP.Request` | `method`\* (GET/POST/PUT/HEAD/DELETE), `url`\*, `body`/`body_b64` (required for POST/PUT), `headers` (max 15, 1024B each), `timeout` (default 15 s), `ssl_ca` | same — total request ≤8192 B |

---

## SECTION 5 — BLU / BTHome (Bluetooth Gateway)

### How Gen2+ Acts as BLE Gateway

A Gen2+ device with BLE enabled scans for BTHome v2 advertisement packets from nearby BLE sensors. Each physical device is represented as a `BTHomeDevice` dynamic component (ID 200–299), and each sensor data stream as a `BTHomeSensor` component.

### BTHome Component (Manager)

**Methods:** `BTHome.GetConfig`, `BTHome.SetConfig`, `BTHome.GetStatus`, `BTHome.AddDevice` (`config`\* with addr/key/name, `id` optional 200–299), `BTHome.DeleteDevice` (`id`\*), `BTHome.AddSensor` (`config`\* with addr/obj_id/obj_idx/name, `id` optional), `BTHome.DeleteSensor` (`id`\*), `BTHome.StartDeviceDiscovery` (`duration` default 30 s), `BTHome.GetObjectInfos` (`obj_ids` array, `offset` optional), `BTHome.ResetEncryptionCounter`

**Status:** discovery state/timing, `errors` (bluetooth_disabled, encryption_counter_near_limit, encryption_counter_exhausted)

**Discovery events:** `device_discovered` (addr, name, RSSI, encryption flag), `discovery_done` (device count)

### BTHomeDevice Component (per physical BLU device)

**Config:** `id`, `name`, `addr` (MAC), `key` (AES hex string|null — for encrypted devices), `meta`

**Status:** `id`, `rssi` (dBm|null), `battery` (%|null), `packet_id` (|null), `last_update_ts`, `key` (bool — key configured), `paired` (bool), `rpc` (bool — device is RPC capable), `rsv` (internal version), `fw_ver`, `errors` (key_missing_or_bad, decrypt_failed, parse_failed, unencrypted_data)

### BTHomeSensor Component (per data object)

**Config:** `id`, `name`, `obj_id` (number — BTHome object ID), `idx` (object index), `addr` (MAC of source device), `meta`

**Status:** `id`, `value` (number|string|bool), `last_update_ts`

**Webhook:** `bthomesensor.value_change` (attr: `value`)

### BTHome obj_id Taxonomy (from BTHome v2 spec)

| Decimal | Hex | Name | Type | Factor | Unit |
|---------|-----|------|------|--------|------|
| 0 | 0x00 | packet_id | uint8 | 1 | — |
| 1 | 0x01 | battery | uint8 | 1 | % |
| 2 | 0x02 | temperature | sint16 | 0.01 | °C |
| 3 | 0x03 | humidity | uint16 | 0.01 | % |
| 4 | 0x04 | pressure | uint24 | 0.01 | hPa |
| 5 | 0x05 | illuminance | uint24 | 0.01 | lx |
| 6 | 0x06 | mass (kg) | uint16 | 0.01 | kg |
| 7 | 0x07 | mass (lb) | uint16 | 0.01 | lb |
| 8 | 0x08 | dewpoint | sint16 | 0.01 | °C |
| 9 | 0x09 | count | uint8 | 1 | — |
| 10 | 0x0A | energy | uint24 | 0.001 | kWh |
| 11 | 0x0B | power | uint24 | 0.01 | W |
| 12 | 0x0C | voltage | uint16 | 0.001 | V |
| 13 | 0x0D | pm2.5 | uint16 | 1 | µg/m³ |
| 14 | 0x0E | pm10 | uint16 | 1 | µg/m³ |
| 15 | 0x0F | generic boolean | uint8 | 1 | — |
| 16 | 0x10 | power (binary) | uint8 | 1 | — |
| 17 | 0x11 | opening | uint8 | 1 | — |
| 18 | 0x12 | co2 | uint16 | 1 | ppm |
| 19 | 0x13 | tvoc | uint16 | 1 | µg/m³ |
| 20 | 0x14 | moisture | uint16 | 0.01 | % |
| 21 | 0x15 | battery (binary) | uint8 | 1 | — |
| 22 | 0x16 | battery_charging | uint8 | 1 | — |
| 23 | 0x17 | carbon_monoxide | uint8 | 1 | — |
| 24 | 0x18 | cold | uint8 | 1 | — |
| 25 | 0x19 | connectivity | uint8 | 1 | — |
| 26 | 0x1A | door | uint8 | 1 | — |
| 27 | 0x1B | garage_door | uint8 | 1 | — |
| 28 | 0x1C | gas | uint8 | 1 | — |
| 29 | 0x1D | heat | uint8 | 1 | — |
| 30 | 0x1E | light | uint8 | 1 | — |
| 31 | 0x1F | lock | uint8 | 1 | — |
| 32 | 0x20 | moisture (binary) | uint8 | 1 | — |
| 33 | 0x21 | motion | uint8 | 1 | — |
| 34 | 0x22 | moving | uint8 | 1 | — |
| 35 | 0x23 | occupancy | uint8 | 1 | — |
| 36 | 0x24 | plug | uint8 | 1 | — |
| 37 | 0x25 | presence | uint8 | 1 | — |
| 38 | 0x26 | problem | uint8 | 1 | — |
| 39 | 0x27 | running | uint8 | 1 | — |
| 40 | 0x28 | safety | uint8 | 1 | — |
| 41 | 0x29 | smoke | uint8 | 1 | — |
| 42 | 0x2A | sound | uint8 | 1 | — |
| 43 | 0x2B | tamper | uint8 | 1 | — |
| 44 | 0x2C | vibration | uint8 | 1 | — |
| 45 | 0x2D | window | uint8 | 1 | — |
| 46 | 0x2E | humidity (8-bit) | uint8 | 1 | % |
| 47 | 0x2F | moisture (8-bit) | uint8 | 1 | % |
| 58 | 0x3A | button (event) | uint8 | 1 | — |
| 59 | 0x3B | command (event) | uint8 | 1 | — |
| 60 | 0x3C | dimmer (event) | uint8 | 1 | — |
| 61 | 0x3D | count (uint16) | uint16 | 1 | — |
| 62 | 0x3E | count (uint32) | uint32 | 1 | — |
| 63 | 0x3F | rotation | sint16 | 0.1 | ° |
| 64 | 0x40 | distance (mm) | uint16 | 1 | mm |
| 65 | 0x41 | distance (m) | uint16 | 0.1 | m |
| 66 | 0x42 | duration | uint24 | 0.001 | s |
| 67 | 0x43 | current | uint16 | 0.001 | A |
| 68 | 0x44 | speed | uint16 | 0.01 | m/s |
| 69 | 0x45 | temperature (0.1) | sint16 | 0.1 | °C |
| 70 | 0x46 | UV index | uint8 | 0.1 | — |
| 71 | 0x47 | volume (0.1L) | uint16 | 0.1 | L |
| 72 | 0x48 | volume (mL) | uint16 | 1 | mL |
| 73 | 0x49 | volume_flow_rate | uint16 | 0.001 | m³/hr |
| 74 | 0x4A | voltage (0.1V) | uint16 | 0.1 | V |
| 75 | 0x4B | gas (m3, 24-bit) | uint24 | 0.001 | m³ |
| 76 | 0x4C | gas (m3, 32-bit) | uint32 | 0.001 | m³ |
| 77 | 0x4D | energy (32-bit) | uint32 | 0.001 | kWh |
| 78 | 0x4E | volume (L, 32-bit) | uint32 | 0.001 | L |
| 79 | 0x4F | water | uint32 | 0.001 | L |
| 80 | 0x50 | timestamp | uint32 | — | Unix ts |
| 81 | 0x51 | acceleration | uint16 | 0.001 | m/s² |
| 82 | 0x52 | gyroscope | uint16 | 0.001 | °/s |
| 83 | 0x53 | text | variable | — | — |
| 84 | 0x54 | raw | variable | — | — |
| 85 | 0x55 | volume_storage | uint32 | 0.001 | L |
| 86 | 0x56 | conductivity | uint16 | 1 | µS/cm |
| 87–91 | 0x57–0x5B | temperature/count variants | sint8/sint16/sint32 | various | °C/— |
| 92 | 0x5C | power (signed) | sint32 | 0.01 | W |
| 93 | 0x5D | current (signed) | sint16 | 0.001 | A |
| 94 | 0x5E | direction | uint16 | 0.01 | ° |
| 95 | 0x5F | precipitation | uint16 | 0.1 | mm |
| 96 | 0x60 | channel | uint8 | 1 | — |
| 97 | 0x61 | rotational_speed | uint16 | 1 | rpm |
| 98–99 | 0x62–0x63 | speed/accel (signed) | sint32 | 0.000001 | m/s, m/s² |
| 100 | 0x64 | light_level | uint8 | 1 | — |
| 101 | 0x65 | settings_revision | uint8 | 1 | — |
| 240–242 | 0xF0–0xF2 | device_type_id, fw_version | various | — | — |

### BluTrv Component (BLU TRV Bridge on Gateway)

**Methods:**

| Method | Params | Description |
|--------|--------|-------------|
| `BluTrv.GetStatus` | `id`\* | Current temp, valve pos, battery, connection metrics |
| `BluTrv.GetConfig` | `id`\* | BT addr, sensor associations |
| `BluTrv.SetConfig` | `id`\*, `config`\* | Modify name etc. |
| `BluTrv.Delete` | `id`\* | Remove BluTrv instance |
| `BluTrv.Call` | `id`\*, `method`\* (Trv.* method), `params` | Proxies RPC to physical TRV |
| `BluTrv.GetRemoteStatus` | `id`\* | Full remote TRV device status |
| `BluTrv.GetRemoteConfig` | `id`\* | Remote TRV configuration |
| `BluTrv.GetRemoteDeviceInfo` | `id`\* | TRV device ID and firmware |
| `BluTrv.UpdateFirmware` | `id`\* | OTA firmware update on paired TRV |
| `BluTrv.CheckForUpdates` | `id`\* | Check available firmware versions |

**BluTrv Status fields:** `target_C`, `current_C`, `pos` (valve %), `errors`, `rsv` (state version — when changes, call GetRemoteStatus)

**Devices:** ShellyBluGwG3, any Gen2+ device with BLE enabled and paired BLU TRV

### BTHomeControl Component

**Methods:** `BTHomeControl.List`, `BTHomeControl.Create` (mappings obj), `BTHomeControl.Update` (`id`\*, mappings), `BTHomeControl.DeleteAll`, `BTHomeControl.StartLearning` (`input_id` or `component_key`), `BTHomeControl.StopLearning`, `BTHomeControl.SetConfig`, `BTHomeControl.GetConfig`, `BTHomeControl.GetStatus`, `BTHomeControl.Enumerate`

**Config:** `id`, `blu_remote_cover_mode` (0=continuous movement, 1=step-based/24 steps=3s)

**Status:** `id`, `learning` object (stage: pairing/press/done/remove/error, err, ts, duration)

---

## SECTION 6 — Gen1 Legacy REST Surface

**Base URL:** `http://<device-ip>/`

**Authentication:** HTTP Basic Auth (`http://user:pass@<ip>/endpoint`) or cookie-based

### Universal Endpoints (all Gen1 devices)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `GET /shelly` | GET | Device identification: type, mac, auth, fw, num_outputs, num_meters, has_update, etc. |
| `GET /status` | GET | Full device state (see below) |
| `GET /settings` | GET/POST | Full device configuration |
| `GET /settings/ap` | GET/POST | WiFi AP config |
| `GET /settings/sta` | GET/POST | WiFi STA config |
| `GET /settings/login` | GET/POST | Authentication config |
| `GET /settings/cloud` | GET/POST | Cloud config |
| `GET /reboot` | GET | Reboot device |
| `GET /ota` | GET | Check/apply OTA update |
| `GET /wifiscan` | GET | Scan for WiFi networks |

### `/status` Response Structure (relay devices)

```
{
  wifi_sta: {connected, ssid, ip, rssi},
  cloud: {enabled, connected},
  mqtt: {connected},
  time: "HH:MM",
  unixtime: number,
  serial: number,
  has_update: bool,
  mac: string,
  relays: [
    {ison, has_timer, timer_started, timer_duration, timer_remaining, overpower, source}
  ],
  meters: [
    {power, overpower, is_valid, timestamp, counters: [f,f,f], total}
  ],
  inputs: [
    {input: 0|1, event: "S"|"SS"|"SSS"|"L"|"SL"|"LS"}
  ],
  temperature: number,          // internal (PlugS/1PM)
  overtemperature: bool,
  tmp: {tC, tF, is_valid},
  uptime: number
}
```

### Control Endpoints by Device Type

**Relay devices (Shelly1, 1PM, 2, 2.5, 4Pro, Plug, PlugS):**

`GET/POST /relay/<N>?turn=on|off|toggle&timer=<s>`

Response: `{ison, has_timer, timer_started_at, timer_duration, timer_remaining, overpower, source}`

**Meter data:**

`GET /meter/<N>`

Response: `{power (W), overpower (W), is_valid, timestamp, counters: [f1min, f2min, f3min], total (Wh)}`

**Energy meter devices (Shelly EM, 3EM):**

`GET /emeter/<N>`

Response: `{power (W), reactive (VAr), apparent (VA), factor (PF), voltage (V), current (A), pf, is_valid, timestamp, total (Wh), total_returned (Wh)}`

`GET /emeter/<N>/em_data.csv` — Historical energy data as CSV (timestamp, active_energy, reactive_energy columns)

**Roller/shutter devices (Shelly2.5 in roller mode):**

`GET/POST /roller/<N>?go=open|close|stop|to_pos&roller_pos=<0-100>&duration=<s>`

Response: `{state: open|close|stop, power, is_valid, safety_switch, overtemperature, stop_reason, last_direction, current_pos, calibrating, positioning}`

`GET /settings/roller/<N>` — Roller-specific config (maxtime, default_state, swap_inputs, etc.)

**Lighting devices (Shelly Dimmer 1/2):**

`GET/POST /light/<N>?turn=on|off|toggle&brightness=<0-100>&transition=<ms>&timer=<s>`

Response: `{ison, mode, brightness, timer_started_at, timer_duration, timer_remaining, has_timer, source}`

**RGBW devices (Shelly RGBW2):**

`GET/POST /color/0?turn=on|off&mode=color|white&red=<0-255>&green=<0-255>&blue=<0-255>&white=<0-255>&gain=<0-100>&brightness=<0-100>&temp=<3000-6500>&transition=<ms>&timer=<s>`

`GET/POST /white/<N>?turn=on|off&brightness=<0-100>&transition=<ms>&timer=<s>` — Per-channel white control

**Bulb/Duo (CCT):**

`GET/POST /light/0?turn=on|off&mode=white&brightness=<0-100>&temp=<3000-6500>&transition=<ms>`

**Webhook/Actions (Gen1):**

`GET /settings/actions` — List configured action URLs

Actions configured per-event type in `/settings` with fields: `btn_on_url`, `btn_off_url`, `out_on_url`, `out_off_url`, `shortpush_url`, `longpush_url`, `btn1_on_url`, `btn1_off_url`, etc. (device-specific). URLs are plain HTTP strings. Since v1.7.0, `http://localhost/` prefix enables self-invocation.

### Gen1 → Gen2+ Component Mapping

| Gen1 Concept | Gen1 Endpoint | Gen2+ Component | Notes |
|---|---|---|---|
| Relay state | `relays[N].ison` | `Switch.GetStatus.output` | |
| Relay meter | `meters[N].power` | `Switch.GetStatus.apower` | |
| Relay total energy | `meters[N].total` (Wh) | `Switch.GetStatus.aenergy.total` | |
| Energy meter | `emeter[N].*` | `EM1.GetStatus.*` or `EM.GetStatus.*` | |
| EM historical | `/emeter/N/em_data.csv` | `EM1Data.GetData` / `EMData.GetData` | |
| Roller position | `rollers[N].current_pos` | `Cover.GetStatus.current_pos` | |
| Roller control | `/roller/N?go=open` | `Cover.Open/Close/GoToPosition` | |
| Light brightness | `lights[N].brightness` | `Light.GetStatus.brightness` | |
| Light color | `/color/0` (RGBW2) | `RGBW.GetStatus` | |
| White channel | `/white/N` (RGBW2) | `Light.GetStatus` | |
| Input state | `inputs[N].input` | `Input.GetStatus.state` | |
| Button event | `inputs[N].event` | `Input` webhook event | |
| Temperature | `tmp.tC` | `Temperature.GetStatus.tC` | |
| Actions/webhooks | `/settings/actions` | `Webhook.*` | Full JS conditions in Gen2 |
| Settings schedules | `/settings` timers | `Schedule.*` | Full cron in Gen2 |

---

## SECTION 7 — JSON-RPC Frame Format, Auth, Error Codes, Rate/Concurrency Limits

### JSON-RPC 2.0 Frame Formats

**Request frame:**
```json
{
  "jsonrpc": "2.0",        // string, optional
  "id": 1,                  // number|string, required (for response matching)
  "src": "user_1",          // string, required (caller identifier)
  "method": "Switch.Set",   // string, required
  "params": {"id": 0, "on": true}  // object, optional
}
```

**Response frame (success):**
```json
{
  "id": 1,
  "src": "shellypro4pm-f008d1d8b8b8",
  "dst": "user_1",
  "result": {"was_on": false}
}
```

**Response frame (error):**
```json
{
  "id": 1,
  "src": "shellypro4pm-f008d1d8b8b8",
  "dst": "user_1",
  "error": {"code": -105, "message": "Bad id=12"}
}
```

### Notification Frames

**NotifyStatus** — partial status changes:
```json
{
  "src": "shellypro4pm-f008d1d8b8b8",
  "dst": "user_1",
  "method": "NotifyStatus",
  "params": {
    "ts": 1631186545.04,
    "switch:0": {"id": 0, "output": true, "source": "button"}
  }
}
```
Use: overlay changes onto known state. Only changed fields included (null = removed key).

**NotifyFullStatus** — complete status (v0.11.0+):
```json
{
  "method": "NotifyFullStatus",
  "params": {
    "ts": 1631186545.04,
    "<component>": { /* full status object */ }
  }
}
```
Emitted: over WebSocket for all devices; over WS/MQTT/UDP for battery devices.

**NotifyEvent** — events not reflected in status (button presses, config changes):
```json
{
  "src": "shellypro4pm-f008d1d8b8b8",
  "dst": "user_1",
  "method": "NotifyEvent",
  "params": {
    "ts": 1631266595.44,
    "events": [{
      "component": "input:0",
      "id": 0,
      "event": "single_push",
      "ts": 1631266595.44
    }]
  }
}
```

### Authentication (Gen2+ — Digest SHA-256, RFC 7616)

**Setup:** `Shelly.SetAuth` with `ha1 = SHA256("admin:<device-id>:<password>")`. Username is always `"admin"`.

**Flow:**
1. Client sends unauthenticated request
2. Device returns HTTP 401 with `WWW-Authenticate: Digest` header (or JSON error frame for WebSocket) containing `auth_type`, `nonce` (base64), `realm` (device ID), `algorithm: SHA-256`
3. Client computes: `ha1 = SHA256("admin:<realm>:<password>")`, `ha2 = SHA256("<HTTP_METHOD>:<URI>")` (HTTP) or `SHA256("dummy_method:dummy_uri")` (WS/other), `response = SHA256("<ha1>:<nonce>:<nc>:<cnonce>:auth:<ha2>")`
4. Client resubmits with `auth` object: `{realm, username: "admin", nonce, cnonce, nc (8-hex padded), response, algorithm: "SHA-256"}`

**Nonce reuse (v2.0.0+):** A single nonce can be reused for up to 30,000 requests within 1 hour by incrementing `nc`. Device maintains circular buffer of 32 nonce entries. `nc` must strictly increase; stale nonce returns 401 with `stale=true`.

**Rate limiting:** 10-minute sliding window with progressive delays: 1–10 fails = no delay; 11–20 = 10 s delay; 21–30 = 30 s delay; 31–40 = 60 s delay; 40+ = 5 min delay. Returns HTTP 429.

**Pre-v2.0.0:** Numeric nonce, no server-side tracking, full 401 round-trip per HTTP request.

### Authentication (Gen1 — Basic Auth)

Standard HTTP Basic Auth. Credentials in URL (`http://user:pass@ip/endpoint`) or `Authorization: Basic` header.

### Error Codes (Gen2+)

| Code | Name | Description |
|------|------|-------------|
| `-103` | INVALID_ARGUMENT | Parameters do not match method spec |
| `-104` | DEADLINE_EXCEEDED | Request timed out (common from HTTP.GET in scripts) |
| `-105` | NOT_FOUND | Specified component instance not found |
| `-108` | RESOURCE_EXHAUSTED | Required resource at limit (e.g., max 20 schedules) |
| `-109` | FAILED_PRECONDITION | Precondition not met (e.g., switch in overpower state) |
| `-114` | UNAVAILABLE | Service unavailable (internal sensor or external service) |

HTTP status codes: `503 Service Unavailable` when concurrency limit exceeded.

### Rate & Concurrency Limits

| Limit | Value |
|-------|-------|
| Concurrent RPC channels | **6** simultaneous non-persistent channels |
| Exceeding concurrency | HTTP 503 returned |
| Max schedules | **20** (all devices) |
| Max webhooks | **20** (regular), **10** (battery devices) |
| Max scripts running | **3** concurrent |
| Max script instances | **10** |
| Max KVS entries | **50** |
| KVS key max length | **42** chars |
| KVS value max length | **253** chars |
| Max webhook URLs | **5** per webhook |
| Max webhook URL length | **300** chars |
| Max schedule calls | **5** per job |
| Max virtual components | **10** (Gen3/Pro Gen2 only) |
| Auth nonce buffer | **32** nonce entries |
| Auth nonce validity | **1 hour**, **30,000** requests per nonce |
| Auth brute-force window | **10-minute** sliding window |

### RPC Channels Summary

| Channel | Type | Auth | Notifications | Notes |
|---------|------|------|---------------|-------|
| HTTP | One-shot | Digest (Gen2) / Basic (Gen1) | No | POST full frame or GET with query params |
| WebSocket | Persistent | Digest | Yes (NotifyStatus/Event/FullStatus) | `ws://<ip>/rpc`; must send valid `src` |
| MQTT | Pub-sub | Broker-level | Yes | `<id>/rpc` in, `<src>/rpc` out, `<id>/events/rpc` notifications |
| UDP | Datagram | None | No | Disabled by default; no delivery guarantee |
| Outbound WS | Persistent outbound | — | Yes (device initiates) | `Ws` component config |

---

## SECTION 8 — Component × Device-Generation Matrix

| Component | Gen1 | Gen2 (Plus/Pro) | Gen3 | Gen4 | BLU |
|-----------|------|-----------------|------|------|-----|
| Switch | ✓ (relay/N) | ✓ | ✓ | ✓ | — |
| Cover | ✓ (roller/N) | ✓ | ✓ | ✓ | — |
| Light | ✓ (light/N, dimmer) | ✓ | ✓ | ✓ | — |
| RGB | ✓ (color/0 RGBW2) | ✓ (Plus RGBW PM) | ✓ | ✓ | — |
| RGBW | ✓ (RGBW2) | ✓ (Plus RGBW PM) | ✓ | ✓ | — |
| CCT | ✓ (Duo/Bulb) | ✓ | ✓ | ✓ | — |
| Input | ✓ (inputs[]) | ✓ | ✓ | ✓ | — |
| PM1 | — | ✓ (Plus1PM etc.) | ✓ | ✓ | — |
| EM (3-phase) | ✓ (3EM) | ✓ (Pro3EM) | — | — | — |
| EM1 (1-phase) | ✓ (Shelly EM) | ✓ (ProEM) | ✓ (EM Gen3) | ✓ | — |
| EMData | — | ✓ (Pro3EM) | — | — | — |
| EM1Data | — | ✓ (ProEM) | ✓ (EM Gen3) | ✓ | — |
| Temperature | ✓ (H&T, Uni) | ✓ | ✓ | ✓ | ✓ (BLU H&T) |
| Humidity | ✓ (H&T) | ✓ | ✓ (HT Gen3) | ✓ | ✓ (BLU H&T) |
| DevicePower | ✓ (battery status) | ✓ (battery devices) | ✓ | ✓ | ✓ |
| Voltmeter | ✓ (Uni analog) | ✓ (via SensorAddon) | ✓ | ✓ | — |
| Smoke | ✓ (Smoke) | ✓ | ✓ | ✓ | — |
| Illuminance | ✓ (Motion, D/W2) | ✓ | ✓ | ✓ | — |
| Trv (BLU TRV) | ✓ (Gen1 TRV — different API) | — (bridge only) | — | — | ✓ (BLU TRV direct) |
| BluTrv (bridge) | — | ✓ (BLE gateway) | ✓ (BluGwG3) | ✓ | — |
| Sys | — | ✓ | ✓ | ✓ | ✓ (partial) |
| WiFi | — | ✓ | ✓ | ✓ | ✓ |
| Eth | — | ✓ (Pro-series) | ✓ (Pro-series) | ✓ | — |
| BLE | — | ✓ | ✓ | ✓ | n/a |
| Cloud | — | ✓ | ✓ | ✓ | ✓ |
| MQTT | — | ✓ | ✓ | ✓ | — |
| Ws (outbound) | — | ✓ | ✓ | ✓ | — |
| Script | — | ✓ | ✓ | ✓ | — |
| Schedule | — | ✓ | ✓ | ✓ | — |
| Webhook | — | ✓ | ✓ | ✓ | — |
| KVS | — | ✓ | ✓ | ✓ | — |
| Virtual components | — | ✓ (Pro only) | ✓ | ✓ | — |
| BTHome | — | ✓ (BLE gateway) | ✓ | ✓ | — |
| BTHomeControl | — | ✓ | ✓ | ✓ | — |
| LNM | — | ✓ (Pro) | ✓ | ✓ | — |
| Matter | — | — | ✓ | ✓ | — |
| Zigbee | — | — | — | ✓ | — |
| Modbus | — | ✓ (Pro3EM, ProEM) | ✓ | ✓ | — |
| KNX | — | ✓ (integration) | ✓ | ✓ | — |
| SensorAddon | — | ✓ (Plus-series) | ✓ | — | — |
| LoRa Add-On | — | — | ✓ | ✓ | — |
| PM1 | — | ✓ | ✓ | ✓ | — |

**Key notes on the matrix:**
- Gen2 = "Plus" and "Pro" firmware families (same API, different hardware)
- Gen3 introduced Matter, LNM, Virtual components on non-Pro devices
- Gen4 added Zigbee, expanded LoRa band plans (US915, BR915-928)
- BLU devices (BLU Button, BLU H&T, BLU Door/Window) expose limited direct Shelly API; accessed primarily as BTHomeSensor data via a gateway host device
- BLU TRV exposes full Trv.* RPC but requires a gateway (BluGwG3 or any Gen2+ with BLE) to proxy via BluTrv.Call
- Slat control (Cover) added for venetian blinds on: Plus2PM, 2PM Gen3, Shutter, Pro2PM, ProDualCoverPM

---

## Key Implementation Notes for MCP Server

1. **Component ID discovery:** Always call `Shelly.GetComponents` first (paginate with `offset`); never hardcode component types for unknown devices.
2. **Profile-aware:** Call `Shelly.ListProfiles` + `Shelly.GetDeviceInfo` (check `profile` field) before assuming component layout on multi-profile devices (Plus2PM, Pro2PM).
3. **Generation detection:** `Shelly.GetDeviceInfo.gen` = 1/2/3/4; drives which API surface to use.
4. **Gen1 normalization:** Use `gen=1` flag to route to REST endpoints vs. JSON-RPC for gen≥2. Field translation table in Section 6.
5. **Battery devices:** Check `DevicePower` presence to detect battery-operated devices; these have `wakeup_reason` in Sys status and reduced webhook limits (10).
6. **SensorAddon:** Presence detected via `Sys.GetConfig.device.addon_type == "sensor"`; peripheral IDs are 100–199, internal are 0–99.
7. **LoRa Addon:** Detected via `Sys.GetConfig.device.addon_type == "LoRa"`.
8. **BTHome sensors:** Use `BTHome.GetObjectInfos` to resolve obj_id metadata at runtime; the obj_id taxonomy above (from bthome.io spec) covers all known types.
9. **Concurrency:** Use a connection pool capped at 6 simultaneous RPC channels per device; queue additional requests.
10. **WebSocket preferred:** For real-time status, use persistent WebSocket (`/rpc`) to receive `NotifyStatus`/`NotifyEvent` pushes rather than polling.
11. **NotifyStatus overlay:** NotifyStatus sends only changed fields; always merge into last-known full state rather than replacing it.
12. **Nonce reuse:** Implement nonce+nc counter tracking per device to avoid per-request 401 round-trips (saves ~50% latency on authenticated devices).
13. **`tag` field:** Available on Switch, Cover, Light, RGB, RGBW (max 20 chars) — useful for attribution/deduplication in MCP context.
14. **`source` field:** Last command origin is always present in status — values include: `init`, `WS_in`, `http`, `mqtt`, `loopback`, `button`, `schedule`, `webhook`, `cloud`, `app`.agentId: a96ad955bdada9939 (use SendMessage with to: 'a96ad955bdada9939' to continue this agent)
<usage>subagent_tokens: 116816
tool_uses: 119
duration_ms: 868208</usage>