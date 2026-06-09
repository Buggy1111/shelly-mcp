# Shelly MCP Server — Post-Launch Roadmap

> What ships **after** v1.0 is public. The build milestones (M0–M5 + scenes + automation) are
> done and live-verified — see `05-BUILD-PLAN.md`. This file tracks deliberate next steps so
> known gaps read as *planned*, not *forgotten*. Same discipline as before: each item has a
> **Definition of Done (DoD)** and isn't "done" until it's green.

## Guiding principle

v1.0 ships as-is. Nothing here blocks the public launch. These are features driven by real use
(and by what competitors are missing), prioritised so the strongest differentiator — **energy
that is actually useful over time** — lands first.

---

## Energy history (the gap found in real use, 2026-06-09)

**The gap.** The server answers *"how much power right now?"* (`shelly_energy_live`) and
*"how much in total?"* (lifetime `aenergy.total`), but **not** *"how much yesterday / this week?"*.
Two distinct causes, two distinct fixes:

### R1 — Local EM/EMData history readout
Devices that **do** keep their own history (Pro 3EM `EMData`, Gen1 `em_data.csv`) expose it only
over a **local** connection — over Cloud you get totals + the last few `by_minute` samples and
nothing more. The plumbing note is already in `shelly_energy_history`'s docstring; this is the
follow-through.
- Read `EMData.GetRecords` / `EMData.GetData` (Pro 3EM) and `GET /emeter/0/em_data.csv` (Gen1 EM)
  over the local backends; normalise into the canonical energy shape.
- Cloud path stays best-effort (totals + recent by-minute) and **says so** — never silently
  returns a flat/empty series as if it were real history.
- **DoD:** on a real EM-class device over LAN, return a correct per-interval series for "today"
  and "this week"; the Cloud path degrades with an explicit note, not a fake zero series.

### R2 — Optional energy logger (for devices with no built-in history)
Plug / PlugS / Plus 1PM (the common case, incl. all four devices here) **don't retain** a daily
series — that history lives only in the Shelly Cloud app. To own it independently:
- Optional background logger: periodically sample `aenergy.total` per device/channel and persist
  to local SQLite; daily/weekly figures come from **deltas** between samples (robust to reboots
  and counter behaviour — store raw totals, compute deltas on read).
- Opt-in (off by default), configurable interval, path under the existing config dir; documented
  as the way to get history for devices that can't provide it themselves.
- **DoD:** with the logger enabled, answer "how much did `mycka`/`televize` use yesterday and
  over the last 7 days?" purely from local data, with **no** dependency on Shelly Cloud.

---

## Other post-launch candidates (unordered, demand-driven)

- **BLU / BTHome** — surface Shelly BLU sensors (motion, door/window, temp/humidity) via a Gen2+
  device acting as a BLE gateway; read tools + webhook/automation hooks.
- **Group / room actions as first-class tools** — today room control means
  `list_devices` → filter by `location` → act N times; a thin `shelly_room_*` helper (built on the
  existing scene engine) would make "turn off the kitchen" one deterministic call.
- **Richer discovery output** — fold `gen`/`model`/`app`/`fw` into `shelly_list_devices` even on
  the Cloud backend where they currently come back `null`.
- **Energy cost helper** — optional tariff (price/kWh) in config so energy tools can answer in
  money, not just kWh. (Asked for in real use — Michal, 2026-06-09.)

---

## What is explicitly **not** planned (for now)

- A hosted/proxy mode (we are deliberately local-first; cloud is a degraded fallback, not a
  product). Revisit only if there's real demand from off-LAN users.
- Re-implementing the Shelly app's full statistics UI — the MCP exposes the data; charting is the
  client's job.

---

*Roadmap opened 2026-06-09, right after v1.0 feature-complete, triggered by a real "show me this
week's TV usage" request that the Cloud path couldn't satisfy. The honest answer became this file.*
