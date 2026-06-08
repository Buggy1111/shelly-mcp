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

## Docs

Full design in [`docs/`](./docs/): overview, architecture (+ADRs), tool surface, security, config/deploy, build plan, and the complete Shelly API catalog.

## License

MIT — see [LICENSE](./LICENSE).
