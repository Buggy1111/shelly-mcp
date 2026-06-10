# shelly-mcp

**MCP server for the entire Shelly smart-home ecosystem** — read, control, and automate Shelly devices of every generation (Gen1 → Gen4; BLU via its gateway or the generic RPC engine, dedicated BLU tools are on the roadmap) from any MCP client (Claude Desktop, Claude Code, Cursor, …). **Local-first** (zero rate-limit, ~10 ms, full API), with **cloud fallback** for off-LAN access.

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

Auto-discovery (mDNS) finds devices on your local subnet — `shelly_discover` and you're running. For named devices ("turn off the kitchen"), devices on other subnets, passwords, or the cloud fallback, create `~/.config/shelly-mcp/config.yaml` (`chmod 600`):

```yaml
devices:
  televize:
    ip: 192.168.0.101
    location: obývák            # lets "turn off the living room" work
    # password: "..."           # only if the device has auth (or env SHELLY_PW_televize)
cloud:
  enabled: false                # optional off-LAN fallback
  # auth_key via env SHELLY_CLOUD_AUTH_KEY
```

Full reference: [`config.example.yaml`](https://github.com/Buggy1111/shelly-mcp/blob/main/config.example.yaml) and [`docs/04-CONFIG-AND-DEPLOY.md`](https://github.com/Buggy1111/shelly-mcp/blob/main/docs/04-CONFIG-AND-DEPLOY.md).

## What data leaves your machine

**None**, beyond the calls to *your own* Shelly devices (on your LAN) and — only if you enable it — *your own* Shelly Cloud account. No telemetry, no phone-home.

## Capabilities (local vs cloud)

| | Local | Cloud |
|---|:--:|:--:|
| Discovery, status, control | ✅ | ⚠️ control + status only |
| Energy live + history | ✅ | ⚠️ live only |
| Automation (schedules/scripts/webhooks/KVS) | ✅ | ❌ |

## Tools, resources & prompts

**Read (safe):** `shelly_version` · `shelly_discover` · `shelly_list_devices` · `shelly_get_info` · `shelly_get_status` (normalized) · `shelly_get_config` (credentials masked) · `shelly_list_components` · `shelly_list_methods`

**Control (audited):** `shelly_switch_set` · `shelly_switch_toggle` · `shelly_light_set` (RGBW/CCT/white) · `shelly_cover_move`

**Energy:** `shelly_energy_live` · `shelly_energy_history`

**Generic engine (total coverage):** `shelly_rpc` (read-only) · `shelly_rpc_write` (mutations, `confirm:true` + data-loss double-gate)

**System / schedules (gated):** `shelly_system_reboot|update|set_auth` · `shelly_schedule_list|create|update|delete`

**Automation (Gen2+ local-only):** `shelly_kvs_*` (key-value store) · `shelly_webhook_*` (event→HTTP) · `shelly_script_*` (on-device JS — list/get_code/create/put_code/start/stop/eval/delete, chunked upload) · `shelly_virtual_*` (virtual components). Deletes + arbitrary-code paths (`script_put_code`/`eval`) are `confirm:true`-gated.

**Scenes (deterministic, named):** `shelly_scene_list|get|run|create|delete` — define a multi-device routine once and run it by name (`shelly_scene_run "film"`), identical every time and schedulable from any client. Stored in `~/.config/shelly-mcp/scenes.yaml` (see [`scenes.example.yaml`](https://github.com/Buggy1111/shelly-mcp/blob/main/scenes.example.yaml)); scenes and schedules accept **only plain control methods** (Switch/Light/RGB(W)/CCT/Cover) — never `Script.Eval`, `SetAuth`, or anything destructive (ADR-007, `docs/06-SCENES.md`).

**Resources:** `shelly://devices`, `shelly://device/{name}/status` — **Prompts:** `shelly_evening_scene`, `shelly_energy_report`, `shelly_diagnose`

> **Safety:** reads are `readOnlyHint`; every mutation is audit-logged; the generic write tool and destructive system tools require explicit `confirm:true`, and irreversible methods (factory reset, wipe-all) need a second `i_understand_data_loss` gate — so even a hijacked LLM can't silently destroy a device.

## Troubleshooting

- **"Device unreachable"** — confirm the IP (`shelly_discover`, your router's client list, or the Shelly app → device → Settings → Device information), and that the machine running the server is on the same LAN. In **WSL/containers, mDNS discovery usually doesn't work** — configure devices by `ip` in the config file instead (that path needs no mDNS).
- **"Auth required"** — the device has a password: add `password:` under the device in the config (or `SHELLY_PW_<name>` env var).
- **Cloud-only device refuses automation tools** — expected: the Shelly Cloud API can't manage schedules/scripts/webhooks/KVS; connect locally for those.
- **Config refuses to load** — if it contains a secret, it must be `chmod 600` (deliberate, fail-closed).

## Docs

Full design in [`docs/`](https://github.com/Buggy1111/shelly-mcp/blob/main/docs/README.md) (indexed): overview, architecture (+ADRs), tool surface, security, scenes, config/deploy, build plan, project log, roadmap, the launch runbook, and the complete Shelly API catalog.

## License

MIT — see [LICENSE](https://github.com/Buggy1111/shelly-mcp/blob/main/LICENSE).
