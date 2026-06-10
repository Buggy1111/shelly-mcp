# Shelly MCP Server — Config, Credentials, Deploy & Distribution

## 1. How a user configures devices (UX)

Three layered sources, merged by `DeviceRegistry` (later overrides earlier):

1. **Auto-discovery (mDNS)** — zero-config for a single subnet. Run `shelly_discover` and devices appear.
2. **Config file** — authoritative, needed for multi-subnet, named devices, and per-device passwords.
3. **Environment variables** — for secrets in headless/CI contexts (override file values).

### `~/.config/shelly-mcp/config.yaml` (enforced `0600`)

```yaml
# Local devices (preferred). Password only if the device has auth enabled.
devices:
  televize:
    ip: 192.168.0.101
    # password: "..."        # optional; or via env SHELLY_PW_televize
  mycka:
    ip: 192.168.1.118        # Gen1 — basic auth user defaults to "admin" if set
  led:
    ip: 192.168.1.116

# mDNS browses the local subnet; devices on other subnets are addressed by `ip` above.
discovery:
  mdns: true

# Optional cloud fallback (off-LAN). The auth_key is account-wide — treat as a secret.
cloud:
  enabled: false
  server: shelly-102-eu.shelly.cloud
  # auth_key via env SHELLY_CLOUD_AUTH_KEY (NOT in this file ideally)

defaults:
  timeout_s: 10
  require_confirm: true       # destructive actions need confirm:true (do not disable lightly)
```

**Credential precedence:** env > file. Passwords are **never** written back to the file by the server, never logged, never returned by any tool (see `03-SECURITY.md §5`).

## 2. Claude Desktop / Code registration

```json
{ "mcpServers": {
    "shelly": { "command": "uvx", "args": ["shelly-mcp"] }
} }
```

Or `pip install shelly-mcp` → `"command": "shelly-mcp"`. Config/creds resolved from the file + env at startup. stdio transport (ADR-004) — nothing to host.

## 3. Local access on Michal's WSL test-bed — *historical; resolved differently*

> **Resolved 2026-06-09 without mirrored networking:** the LAN was flattened onto one subnet (`192.168.0.x`) and WSL reaches the devices through the Windows host — both local backends were live-verified that way. The mirrored-networking recipe below is kept as a fallback for setups where flattening isn't an option.

**Problem (as originally stated):** WSL runs in **NAT mode** (Claude Code sees `172.24.x`, devices live on `192.168.0/1.x`) → the local backend can't reach the LAN. Only the cloud backend is testable today.

**Fix (one-time):** enable **mirrored networking** so WSL shares the Windows host's LAN identity.

`C:\Users\micha\.wslconfig`:
```ini
[wsl2]
networkingMode=mirrored
```
Then from **Windows** (PowerShell/CMD): `wsl --shutdown`, reopen WSL. After that the local backend reaches all four devices directly (~10 ms, full API incl. automations).

> **Senior note — deliberately NOT done yet.** Changing networking mode restarts WSL (kills the session) and can perturb the current Hermes/Docker setup. It's only needed when we begin *local* testing (coding phase). We pull this trigger together when we start the build — not during the docs phase. The exact file content above is ready to drop in. Reversible: delete the file + `wsl --shutdown` to return to NAT.

Until then: the cloud backend (existing `auth_key`) validates the Cloud path; local path is validated right after the switch.

## 4. Distribution channels

Primary model: **bring-your-own-credentials, runs locally** (stdio). Sequence proven on `anonymize-mcp`:

| Channel | Fit | Action |
|---|---|---|
| **MCP Registry** | ✅ ideal (metadata-only, points to PyPI) | `server.json` (`io.github.Buggy1111/shelly-mcp` — case-sensitive) + GitHub OIDC. Auto-ingested by PulseMCP |
| **PyPI** | ✅ the actual package | `pip install` / `uvx shelly-mcp`; trusted publishing (OIDC, no token in CI) |
| **Glama** | ✅ | `glama.json` + strong tool descriptions → quality ≥ B (target A like anonymize) |
| **awesome-mcp-servers** | ✅ | PR to "Home Automation & IoT" with Glama badge |
| **mcp.so** | ✅ | GitHub-issue submission |
| **Smithery** | ❌ skip | killed stdio (Sept 2025); needs hosting/MCPB — bad fit for local/BYO-creds (same as anonymize) |
| **Apify** | ⚠️ partial — see §5 | only the cloud-mode path can be hosted |

## 5. Apify (Michal's request: "dáme to i do Apify") — VERIFIED 2026

Apify officially supports publishing **third-party MCP servers as Actors** (Docker containers) — there's a curated `apify/actor-mcp-servers` repo and a dedicated **MCP-servers Store category**. Mechanics confirmed:

- **Hosting:** an Actor in **Standby mode** runs a persistent HTTP server at a stable URL `https://you--shelly-cloud.apify.actor/mcp`. **Transport = Streamable HTTP** (SSE was removed 2026-04-01; stdio is local-dev only).
- **Official Python FastMCP Actor template** exists (`apify.com/templates/python-mcp-empty`) — `FastMCP` + Uvicorn + `apify` SDK out of the box → **low friction** (~2–4 days for a cloud-mode Actor).
- **Secrets:** Actor input field with `"isSecret": true` → AES-256-GCM + per-Actor RSA, decrypted only inside the run, redacted from logs. Perfect for the Shelly `auth_key`.
- **Monetization:** **Pay-Per-Event** (charge `Actor.charge(...)` per tool call), 80/20 dev split, no upfront cost, Apify handles billing/tax. (Monthly *rental* model is sunset — don't use it.)
- **Discovery bonus:** the Actor also becomes callable via Apify's central `mcp.apify.com` hub.

**The hard constraint (CONFIRMED absolute):** an Apify Actor runs in Apify's datacenter and **physically cannot route to a home LAN** (RFC-1918 private IPs). No proxy/standby/tunnel feature changes this. → **Only the CloudBackend path works on Apify** (user's `auth_key`, internet → shelly.cloud → device); the local-first core + all automations (scripts/schedules/webhooks/KVS) **cannot** run hosted.

**Decision:** ship a thin **`shelly-cloud` Actor** as a **secondary, cloud-only listing**, NOT the flagship.
- Wraps only CloudBackend: list / control / live status via `auth_key`.
- First-mover — no Shelly/IoT MCP exists on Apify Store today.
- README must state plainly: *"Shelly Cloud control via MCP, no local network needed — for direct-LAN, automations, scripts and energy history use the local `uvx shelly-mcp` install."* (honest, per `[[feedback_thorough_verify]]`).
- **Disclose limits:** cloud-only, requires Shelly Cloud account + token, higher latency (cloud round-trip vs ~10 ms LAN), 1 req/s cloud rate-limit, per-call cost.
- **Sequencing:** build *after* the local flagship v1.0 ships — it reuses CloudBackend, so it's a small wrapper, not parallel work.

## 6. Release checklist (per version)

1. `code-audit` + `owasp-security` on the diff; no secrets in repo/history; versions pinned.
2. Unit + contract + eval tests green (contract = Michal's real Gen1+Gen2 fixtures).
3. Bump version; build; PyPI trusted-publish.
4. Update `server.json` → MCP Registry; verify PulseMCP pickup.
5. README "what data leaves your machine" section accurate (no telemetry).
6. Glama re-index; awesome-mcp PR if new major; (later) Apify cloud-Actor if pursued.
