# Shelly MCP Server — Tool Surface

> Every MCP tool, its inputs, outputs, and annotations. Naming convention: `shelly_<group>_<verb>` (consistent prefix → discoverability, per mcp-builder). All inputs are Pydantic-validated; all outputs use `structuredContent` + a human-readable text summary.
>
> **Annotation legend:** RO = `readOnlyHint`, D = `destructiveHint`, I = `idempotentHint`, OW = `openWorldHint`. ⚠️ = requires `confirm: true`.

## Tier 1 — Generic engine (v1.0, total coverage)

| Tool | Annot. | Inputs | Returns |
|---|---|---|---|
| `shelly_version` | RO | — | `{name, version}` — server health check |
| `shelly_discover` | RO, OW | `timeout_s?: float=5`, `use_cloud?: bool` | list of `DeviceIdentity` (id, name, ip, gen, model, mac, online, auth_needed). mDNS browses the local subnet; off-subnet devices are addressed by configured `ip` |
| `shelly_list_devices` | RO | — | configured + discovered devices from the registry |
| `shelly_get_info` | RO | `device: str` (name\|id\|ip) | `DeviceIdentity` + firmware, profile, available updates |
| `shelly_get_status` | RO | `device: str`, `component?: str` | **normalized** canonical status (+`raw`) |
| `shelly_get_config` | RO | `device: str`, `component?: str` | config with credential fields masked as `***` (Gen1 `/settings` carries cleartext Wi-Fi/MQTT secrets — they never reach the model) |
| `shelly_list_components` | RO | `device: str` | components present on *this* device |
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
| `shelly_energy_history` | RO | `device`, `channel?: int` | best-effort history: lifetime totals always, recent `aenergy.by_minute` series when the device exposes one, with an honest `degraded` list otherwise. (Richer queries — `EMData.GetData`/CSV ranges — are a roadmap item) |

## Tier 2 — Schedules (v1.0)

| Tool | Annot. | Inputs | Returns |
|---|---|---|---|
| `shelly_schedule_list` | RO | `device` | list of schedules (id, enable, timespec, calls) |
| `shelly_schedule_create` | I | `device`, `timespec: str` (6-field cron, int DOW 0-6), `calls: list[{method, params}]`, `enable?: bool=true` | `{id}`. Validates ≤20/device, validates timespec, and every call against the **control-method allowlist** (Switch/Light/RGB/RGBW/CCT/Cover) — a schedule can't smuggle `FactoryReset` or `Script.Eval` past the confirm gates (03-SECURITY §5.3) |
| `shelly_schedule_update` | I | `device`, `id: int`, …fields | `{ok}` |
| `shelly_schedule_delete` | D, ⚠️ | `device`, `id: int`, `confirm: bool` | `{ok}` |

## Tier 2 — Scenes (v1.0) — server-side named, deterministic

Server-defined named scenes: a saved, ordered batch of `{device, method, params}` run by name — deterministic, schedulable, identical across clients. Stored in a dedicated `scenes.yaml` (atomic write, fail-soft read), non-destructive by construction. Full design: `06-SCENES.md` / ADR-007.

| Tool | Annot. | Inputs | Returns |
|---|---|---|---|
| `shelly_scene_list` | RO | — | each scene's name, description, action count |
| `shelly_scene_get` | RO | `name: str` | the scene's full ordered actions (or error + available names) |
| `shelly_scene_run` | (mutating, audited) | `name: str` | per-action `{device, method, ok, error?}` + overall `status: ok\|partial\|failed`. Best-effort sequential — a failed action never aborts the rest; re-run a partial later (idempotent) |
| `shelly_scene_create` | I | `name: str`, `actions: list[{device, method, params}]`, `description?: str`, `overwrite?: bool=false` | `{saved, actions, warnings?}`. Validates: every device known, every method on the **control-method allowlist** (Switch/Light/RGB/RGBW/CCT/Cover — no `Script.*`, no `*.SetAuth`); warns on non-idempotent `.Toggle`; refuses an existing name unless `overwrite` |
| `shelly_scene_delete` | D, ⚠️ | `name: str`, `confirm: bool` | `{deleted, confirmed}` |

> `scene_run` needs **no** confirm gate: scenes accept only allowlisted control methods at create time, so a scheduled/LLM-run scene can't reach `FactoryReset`, `Script.Eval`, or `Shelly.SetAuth` (LLM06/ASI02).

## Tier 2 — Automation (v1.0): KVS / Webhook / Script / Virtual

Gen2+ local-only (cloud → `UnsupportedOnCloud`). Reads are RO; mutations audited; **deletes confirm-gated**; the **arbitrary-code** paths (`script_put_code`, `script_eval`) are confirm-gated too (ASI05/LLM05 — running code on the device).

| Tool | Annot. | Inputs | Returns |
|---|---|---|---|
| `shelly_kvs_list` | RO | `device`, `match?: str="*"` | `{keys: {key→etag}, rev}` |
| `shelly_kvs_get` | RO | `device`, `key` | `{value, etag}` |
| `shelly_kvs_set` | I | `device`, `key`, `value: any` | `{etag, rev}` |
| `shelly_kvs_delete` | D, ⚠️ | `device`, `key`, `confirm` | `{rev}` |
| `shelly_webhook_list` | RO | `device` | `hooks[]` |
| `shelly_webhook_create` | I | `device`, `event`, `cid: int`, `urls: [str] (1-5, absolute http(s) only)`, `enable?`, `name?`, `condition?`, `repeat_period?` | `{id, rev}` |
| `shelly_webhook_update` | I | `device`, `id: int`, …fields | `{rev}` |
| `shelly_webhook_delete` | D, ⚠️ | `device`, `id: int`, `confirm` | `{rev}` |
| `shelly_script_list` | RO | `device` | `scripts[]` (id, name, enable, running) |
| `shelly_script_get_code` | RO | `device`, `id: int` | `{code}` (reassembles paginated `GetCode`) |
| `shelly_script_create` | I | `device`, `name?` | `{id}` |
| `shelly_script_put_code` | D, ⚠️ | `device`, `id: int`, `code`, `append?: bool`, `confirm` | `{chunks, len}` — chunks code into ≤1 KB `PutCode` calls |
| `shelly_script_start` / `_stop` | (stateful) | `device`, `id: int` | `{was_running}` |
| `shelly_script_eval` | D, ⚠️ | `device`, `id: int`, `code`, `confirm` | `{result}` — evaluates an expression in the running script |
| `shelly_script_delete` | D, ⚠️ | `device`, `id: int`, `confirm` | `null` |
| `shelly_virtual_list` | RO | `device` | dynamic components (`Shelly.GetComponents dynamic_only`) |
| `shelly_virtual_add` | I | `device`, `type` (boolean/number/text/enum/button/group), `config?: dict`, `id?: int 200-299` | `{id}` |
| `shelly_virtual_delete` | D, ⚠️ | `device`, `key` (`<type>:<cid>`), `confirm` | `null` |

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
