# Shelly MCP Server — Tool Surface

> Every MCP tool, its inputs, outputs, and annotations. Naming convention: `shelly_<group>_<verb>` (consistent prefix → discoverability, per mcp-builder). All inputs are Pydantic-validated; all outputs use `structuredContent` + a human-readable text summary.
>
> **Annotation legend:** RO = `readOnlyHint`, D = `destructiveHint`, I = `idempotentHint`, OW = `openWorldHint`. ⚠️ = requires `confirm: true`.

## Tier 1 — Generic engine (v1.0, total coverage)

| Tool | Annot. | Inputs | Returns |
|---|---|---|---|
| `shelly_discover` | RO, OW | `subnets?: list[str]`, `timeout_s?: int=5`, `use_cloud?: bool` | list of `DeviceIdentity` (id, name, ip, gen, model, mac, online, auth_needed) |
| `shelly_list_devices` | RO | — | configured + discovered devices from the registry |
| `shelly_get_info` | RO | `device: str` (name\|id\|ip) | `DeviceIdentity` + firmware, profile, available updates |
| `shelly_get_status` | RO | `device: str`, `component?: str` | **normalized** canonical status (+`raw`) |
| `shelly_get_config` | RO | `device: str`, `component?: str` | config (normalized where sensible, else raw) |
| `shelly_list_components` | RO | `device: str`, `dynamic_only?: bool` | components present on *this* device (+ each one's available methods) |
| `shelly_list_methods` | RO | `device: str` | ACL-filtered RPC methods the device supports |
| `shelly_rpc` | RO, OW | `device: str`, `method: str`, `params?: dict` | raw RPC result. **Read-only guard:** only `*.Get*`/`*.List*`/`*.Check*` methods accepted; anything else → error pointing to `shelly_rpc_write` |
| `shelly_rpc_write` | D, OW, ⚠️ | `device: str`, `method: str`, `params?: dict`, `confirm: bool` | raw RPC result. Any mutating method. Refuses without `confirm:true`; refuses `FactoryReset`/`ResetWiFiConfig` unless `params.i_understand_data_loss:true`. Audit-logged |

## Tier 2 — Typed control (v1.0)

| Tool | Annot. | Inputs | Returns |
|---|---|---|---|
| `shelly_switch_set` | I | `device`, `channel?: int=0`, `on: bool`, `toggle_after_s?: int` | `ChannelState` (post-action) |
| `shelly_switch_toggle` | (not idemp.) | `device`, `channel?: int=0` | `ChannelState` |
| `shelly_light_set` | I | `device`, `channel?: int=0`, `on?: bool`, `brightness?: int 0-100`, `rgb?: [int,int,int]`, `white?: int`, `temp_k?: int`, `transition_s?: float` | `LightState`. Normalizes Gen1 `/color`,`/light`,`/white` ↔ Gen2 `Light/RGB/RGBW/CCT.Set` |
| `shelly_cover_move` | (stateful) | `device`, `channel?: int=0`, `action: open\|close\|stop`, `position?: int 0-100` | `CoverState` |
| `shelly_system_reboot` | D, ⚠️ | `device`, `confirm: bool`, `delay_ms?: int` | `{ok, restart_required}` |
| `shelly_system_update` | D, ⚠️ | `device`, `confirm: bool`, `channel?: stable\|beta` | `{ok, target_version}` |
| `shelly_system_set_auth` | D, ⚠️ | `device`, `confirm: bool`, `password: str` | `{ok}` (digest enable/rotate) |

## Tier 2 — Energy (v1.0)

| Tool | Annot. | Inputs | Returns |
|---|---|---|---|
| `shelly_energy_live` | RO | `device`, `channel?: int` | `EnergyReading` — power_w, voltage, current, pf, freq, total_wh, ret_total_wh (per phase for EM). `None` where unsupported (Gen1) |
| `shelly_energy_history` | RO | `device`, `from_ts?: int`, `to_ts?: int` (default last 24 h), `resolution?: minute\|hour\|day` | `EnergyHistory`. Pro 3EM → `EMData.GetData`/CSV; per-switch → `aenergy.by_minute`; Gen1 → `/emeter/N/em_data.csv` or `meters[].total` deltas. Degrades gracefully per device |

## Tier 2 — Schedules (v1.0)

| Tool | Annot. | Inputs | Returns |
|---|---|---|---|
| `shelly_schedule_list` | RO | `device` | list of schedules (id, enable, timespec, calls) |
| `shelly_schedule_create` | I | `device`, `timespec: str` (6-field cron, int DOW 0-6), `calls: list[{method, params}]`, `enable?: bool=true` | `{id}`. Validates ≤20/device, validates timespec, validates each call against method registry |
| `shelly_schedule_update` | I | `device`, `id: int`, …fields | `{ok}` |
| `shelly_schedule_delete` | D, ⚠️ | `device`, `id: int`, `confirm: bool` | `{ok}` |

## v1.1 — Automation (planned)

`shelly_webhook_{list,create,update,delete}` · `shelly_script_{list,get_code,create,upload,start,stop,eval,delete}` (chunked `PutCode`) · `shelly_kvs_{get,set,list,delete}` · `shelly_virtual_{add,delete,list}`. Same gating rules: reads RO, mutations gated, `script_eval`/`script_upload` are D+⚠️ (arbitrary code on device → ASI05/LLM05).

## v1.2 — BLU / Matter / Zigbee (planned)

`shelly_bthome_{discover,add_device,add_sensor,list}` · `shelly_blutrv_{status,set_target}` · `shelly_matter_*` · `shelly_zigbee_*`.

## MCP resources & prompts (beyond tools)

MCP has three primitives — tools, **resources**, **prompts**. For "everything possible" + a higher Glama score we expose all three:

**Resources** (read-only, addressable context the client can attach):
- `shelly://devices` — the current registry (all devices + identity + online state) as a resource, so a client can pin the fleet into context without a tool call.
- `shelly://device/{name}/status` — live normalized status of one device as a resource.
- `shelly://device/{name}/components` — capability map of one device.

Resources are ideal for "ambient" state the LLM should see; tools are for actions. (v1.0: `shelly://devices` + per-device status; rest as polish.)

**Prompts** (pre-built, parameterized workflows the user can invoke):
- `shelly_evening_scene` — turn configured lights warm-white at a chosen brightness, plugs off.
- `shelly_energy_report` — summarize today's consumption across the fleet.
- `shelly_diagnose` — check every device's online state, firmware updates, and error fields.

Prompts make the server feel "luxusní" out of the box and are a cheap differentiator (no competitor offers any). (v1.1 — after the tool surface is stable.)

## Design notes (mcp-builder)

- **Concise descriptions, focused returns.** Status tools accept `component?` to avoid dumping the whole device when one channel is asked for.
- **Actionable errors.** `UnsupportedOnCloud` → "this device is only reachable via cloud, which can't do X; connect locally". `UnsupportedOnGeneration` → "Gen1 device has no voltage sensor". `AuthRequired` → "device needs a password; add it to config under devices.<name>.password".
- **Pagination.** `shelly_list_components` / `list_methods` paginate via `Shelly.GetComponents {offset}` for big devices (Wall Display).
- **structuredContent** for every tool so clients can post-process; text summary stays short.
- **`confirm` gate is server-side**, not a description-only convention — the tool returns a refusal + a preview of what would happen when `confirm` is absent.
