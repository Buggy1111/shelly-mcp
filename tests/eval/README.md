# Eval suite (mcp-builder Phase 4)

`evaluation.xml` holds 10 read-only questions an LLM should answer correctly using
**only** the server's tools — the mcp-builder Phase 4 quality bar.

Unlike `tests/unit` and `tests/contract` (which run offline in CI), the eval runs
against the **live MCP** connected to a real Shelly test-bed, because the answers come
from real devices. It is *not* collected by pytest.

**How to run:** point an MCP client (Claude Desktop/Code) at the server with the real
config, then ask each `<question>`; score the reply against the `<answer>` ground
truth. A few answers (subnet count, available firmware, hottest device) depend on live
state at run time and are noted as such.

The questions deliberately exercise the hard parts: Gen1↔Gen2 normalization, the
transport-dependent Gen1 energy unit (ADR-005), `None` ≠ fake-zero on Gen1, and
capability honesty (Gen1 plugs report no voltage/current).
