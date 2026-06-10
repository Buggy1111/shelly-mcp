# Shelly MCP Server — Public Launch Checklist

> The exact runbook to take `shelly-mcp` from a private repo to publicly installable
> (`uvx shelly-mcp`) and listed on the MCP marketplaces. Items marked **[x]** were verified
> locally on 2026-06-09 (overnight prep, no push). Items marked **[ ]** need Michal — they
> require a `git push`, a public repo, or an external account/token. Work top to bottom.

---

## 0. Pre-flight — verified locally 2026-06-09, re-verified 2026-06-10 after the audit fixes

> **2026-06-10:** a pre-launch audit found two confirm-gate bypasses (destructive methods via
> `schedule_create`; `Script.Eval`/`SetAuth` via scenes) — fixed on `auto/audit-fixes` along with
> config redaction, webhook URL validation, a circular import, and a docs pass. Re-run `uv build`
> before publishing — the previously built `dist/` artifacts predate these fixes.

- [x] **Tests green:** `243 passed` (`uv run pytest -q`).
- [x] **Lint clean:** `ruff check .` → all checks passed.
- [x] **Types clean:** `mypy` (`--strict`) → no issues in 49 source files.
- [x] **Tool surface matches docs:** 47 tools + 2 resources (1 static + 1 template) + 3 prompts,
      confirmed from the live-registered server, not just the docstrings.
- [x] **Package builds:** `uv build` → `shelly_mcp-0.1.0-py3-none-any.whl` + `.tar.gz`.
- [x] **Distribution metadata valid:** `uvx twine check dist/*` → both PASSED.
- [x] **Clean-room install works (over the wire):** wheel installed into a fresh `python -m venv`
      (deps resolve from `pyproject` alone); the `shelly-mcp` console script serves a real MCP
      `initialize` + `tools/list` (47) over stdio; and a `tools/call shelly_list_devices` with **no
      config** returns a clean, actionable error (no traceback), not a crash. `serverInfo.version`
      correctly reports `0.1.0`.
- [x] **Version consistent:** `0.1.0` across `pyproject.toml`, `server.json`, `__init__.py`.
- [x] **Docs reconciled:** test count (199 → 243 after the 2026-06-10 audit fixes) and competitive section refreshed.

> **Nothing below was done autonomously** — these are the push/account-gated steps for the morning.

### Known advisory (pre-checked 2026-06-09)

`pip-audit` reports **one** vulnerability: `diskcache 5.6.3` — **CVE-2025-69872**. It is a
**transitive** dependency (`fastmcp[disk]` → `py-key-value-aio[disk]` → `diskcache`), is **not
imported by any shelly-mcp code**, and currently has **no fixed version published**. Stance:
**not a launch blocker** (it's not on our code path); track it and pick up the fix once `diskcache`
ships one or `fastmcp` drops the `[disk]` extra. Our own code is clean — no secrets, no shell/SQL/
command-injection vectors, no TLS bypass, no bare excepts, no debug output; every mutating /
destructive / arbitrary-code tool is `confirm`-gated and covered by tests.

---

## 1. Decisions to make first (5 min)

- [ ] **Version + maturity wording.** Currently `0.1.0` + `Development Status :: 3 - Alpha` +
      "🚧 Alpha" in README — all consistent and honest. Option B is `1.0.0` / Beta for a more
      confident first impression. *Recommendation: ship `0.1.0`/Alpha — it's truthful (zero external
      users yet) and lets `1.0.0` mean "validated in the wild". Bump later, cheaply.*
      → If you change it, update **all three**: `pyproject.toml`, `server.json` (×2: top + package),
      `__init__.py`, plus the classifier.
- [ ] **Stamp the changelog.** Rename `## [Unreleased]` → `## [0.1.0] — 2026-06-10` (today's date)
      at tag time, so the release notes are pinned to the version.

## 2. Make the repo public

- [ ] `gh repo edit Buggy1111/shelly-mcp --visibility public --accept-visibility-change-warnings`
      (or via the GitHub web UI → Settings → Danger Zone).
- [ ] Confirm CI passes on the public repo (the badge / Actions tab is green on `main`).
- [ ] **DoD:** repo is public, CI green, README renders correctly on GitHub.

## 3. PyPI — one-time trusted-publisher setup (no token needed)

`release.yml` already uses **OIDC trusted publishing** (no API token in the repo). For the first
release PyPI needs a *pending publisher* registered:

- [ ] On <https://pypi.org> → *Your projects* → *Publishing* → **Add a pending publisher**:
  - PyPI Project Name: `shelly-mcp`
  - Owner: `Buggy1111` · Repository: `shelly-mcp`
  - Workflow filename: `release.yml`
  - Environment name: `pypi`  *(matches `environment: name: pypi` in `release.yml`)*
- [ ] **DoD:** the pending publisher is saved (the actual publish happens at the tag step below).

## 4. Tag the release → CI publishes everything

The push of a `v*` tag triggers `release.yml` (build → publish to PyPI → create a GitHub release).

- [ ] `git checkout main && git merge --ff-only auto/launch-prep`  *(fold in tonight's prep)*
- [ ] Stamp the changelog (item 1), commit.
- [ ] `git push origin main`
- [ ] `git tag v0.1.0 && git push origin v0.1.0`
- [ ] Watch the run: `gh run watch` — confirm **publish-pypi** and **github-release** both go green.
- [ ] **DoD:** `release.yml` succeeds; the GitHub release exists with auto-generated notes.

## 5. Verify the published package (clean room)

- [ ] In a fresh shell, no local checkout on PATH:
      `uvx --refresh shelly-mcp --help` *(or import-smoke via `uv run --with shelly-mcp ...`)*.
- [ ] Register in a real client and read one device end-to-end (e.g. `shelly_list_devices`).
- [ ] **DoD:** a stranger could `uvx shelly-mcp` and it works — verified from outside the repo.

## 6. MCP Registry

- [x] **Namespace casing — verified correct (2026-06-09), do NOT change.** `server.json` is
      `io.github.Buggy1111/shelly-mcp`. The registry builds the publish permission from your
      **canonical GitHub login** (`user.Login` → `io.github.Buggy1111/*`) and matches it with a
      **case-sensitive** prefix check (`internal/auth/jwt.go` `isResourceMatch` → `strings.HasPrefix`,
      no lowercasing). Confirmed `gh api user --jq .login` = `Buggy1111` (capital B). Lowercasing it
      to `buggy1111` would make the publish **fail** authorization. *(Closes pending launch item #1.)*
- [ ] Publish with the `mcp-publisher` CLI: `mcp-publisher login github` → `mcp-publisher publish`
      (follow the current registry docs; the `server.json` schema is already
      `2025-12-11`). 
- [ ] **DoD:** the server resolves in the MCP Registry under the correct namespace.

## 7. Glama

- [ ] `glama.json` (maintainer = `Buggy1111`) is already in the repo root; Glama auto-crawls public
      GitHub + PyPI. After §2 + §4, confirm the listing appears and the quality grade is sane.
- [ ] **DoD:** `shelly-mcp` shows up in Glama's "Home Automation & IoT" with a green/A grade.

## 8. awesome-mcp-servers

- [ ] Open a PR to `punkpeye/awesome-mcp-servers` adding `shelly-mcp` under Home Automation / IoT
      (one line, alphabetical, matching their entry format — mirror the `anonymize-mcp` PR style that
      already merged).
- [ ] **DoD:** PR opened and passes their lint; merge is on their cadence.

## 9. Auto-crawled catalogs (no action, just verify later)

- [ ] PulseMCP / mcp.so pick up public + PyPI servers automatically. Re-check in a few days that
      `shelly-mcp` appears; nudge only if it doesn't.

## 10. Announce (optional, your call / timing)

- [ ] r/selfhosted + r/Shelly (Reddit) — same lowercase, no-AI-slop style that works for you
      (see the Reddit lessons in memory; let it read human).
- [ ] LinkedIn CZ — the "local-first Shelly automation from any LLM" angle; ties into the
      practitioner/founder brand. Optional video via Higgsfield later.

---

## Rollback / safety notes

- A bad PyPI release **can't be overwritten** — you'd need `0.1.1`. So get §5's clean-room check
  right *before* trusting the tag; if something's wrong, fix forward with a patch version.
- Making the repo public is reversible (back to private), but anything pushed public should be
  assumed cached/cloned. The security audit already confirmed **no secrets in git history**.
- The `v*` tag is the only thing that triggers publishing — nothing publishes from a plain push to
  `main`, so merging tonight's prep branch first is safe.

---

*Prepared 2026-06-09 (overnight) on branch `auto/launch-prep`. Everything that could be verified
without a push is ticked; the rest is sequenced for a clean morning launch.*
