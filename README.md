# shelly-mcp

**MCP server for the entire Shelly smart-home ecosystem** — read, control, and automate Shelly devices of every generation (Gen1 → Gen4 + BLU) from any MCP client (Claude Desktop, Claude Code, Cursor, …). **Local-first** (zero rate-limit, ~10 ms, full API), with **cloud fallback** for off-LAN access.

> ⚠️ **Unofficial community project.** Not affiliated with, endorsed by, or sponsored by Allterco Robotics / Shelly. "Shelly" is a trademark of its respective owner.

> 🚧 **Alpha / in development.** See `docs/` for the full design.

## Why

The only existing Shelly MCP servers are cloud-only and minimal. `shelly-mcp` unifies **Gen1 and Gen2+** behind one tool surface, covers **energy monitoring** and **automation** (schedules, scripts, webhooks, KVS), and auto-discovers any device's capabilities — including hardware released after this server was written.

## Install

```bash
uvx shelly-mcp          # or: pip install shelly-mcp
```

Register in your MCP client:

```json
{ "mcpServers": { "shelly": { "command": "uvx", "args": ["shelly-mcp"] } } }
```

## Configure

Auto-discovery (mDNS) finds devices on your LAN. For named devices, multiple subnets, or auth, use `~/.config/shelly-mcp/config.yaml` (see `docs/04-CONFIG-AND-DEPLOY.md`).

## What data leaves your machine

**None**, beyond the calls to *your own* Shelly devices (on your LAN) and — only if you enable it — *your own* Shelly Cloud account. No telemetry, no phone-home.

## Capabilities (local vs cloud)

| | Local | Cloud |
|---|:--:|:--:|
| Discovery, status, control | ✅ | ⚠️ control + status only |
| Energy live + history | ✅ | ⚠️ live only |
| Automation (schedules/scripts/webhooks/KVS) | ✅ | ❌ |

## Tools, resources & prompts

**Read (safe):** `shelly_discover` · `shelly_list_devices` · `shelly_get_info` · `shelly_get_status` (normalized) · `shelly_get_config` · `shelly_list_components` · `shelly_list_methods`

**Control (audited):** `shelly_switch_set` · `shelly_switch_toggle` · `shelly_light_set` (RGBW/CCT/white) · `shelly_cover_move`

**Energy:** `shelly_energy_live` · `shelly_energy_history`

**Generic engine (total coverage):** `shelly_rpc` (read-only) · `shelly_rpc_write` (mutations, `confirm:true` + data-loss double-gate)

**System / schedules (gated):** `shelly_system_reboot|update|set_auth` · `shelly_schedule_list|create|update|delete`

**Automation (Gen2+ local-only):** `shelly_kvs_*` (key-value store) · `shelly_webhook_*` (event→HTTP) · `shelly_script_*` (on-device JS — list/get_code/create/put_code/start/stop/eval/delete, chunked upload) · `shelly_virtual_*` (virtual components). Deletes + arbitrary-code paths (`script_put_code`/`eval`) are `confirm:true`-gated.

**Scenes (deterministic, named):** `shelly_scene_list|get|run|create|delete` — define a multi-device routine once and run it by name (`shelly_scene_run "film"`), identical every time and schedulable from any client. Stored in `~/.config/shelly-mcp/scenes.yaml` (see `scenes.example.yaml`); non-destructive by construction (ADR-007, `docs/06-SCENES.md`).

**Resources:** `shelly://devices`, `shelly://device/{name}/status` — **Prompts:** `shelly_evening_scene`, `shelly_energy_report`, `shelly_diagnose`

> **Safety:** reads are `readOnlyHint`; every mutation is audit-logged; the generic write tool and destructive system tools require explicit `confirm:true`, and irreversible methods (factory reset, wipe-all) need a second `i_understand_data_loss` gate — so even a hijacked LLM can't silently destroy a device.

## Docs

Full design in [`docs/`](./docs/): overview, architecture (+ADRs), tool surface, security, config/deploy, build plan, and the complete Shelly API catalog.

## License

MIT — see [LICENSE](./LICENSE).
