"""Tests for v1.1 automation tools — kvs / webhook / script / virtual.

Covers reads, audited mutations, the confirm gates (delete + arbitrary-code paths), input
validation, and Script.PutCode chunking + GetCode reassembly against the fake backend.
"""

from __future__ import annotations

from typing import Any

from shelly_mcp.tools.kvs import (
    shelly_kvs_delete,
    shelly_kvs_get,
    shelly_kvs_list,
    shelly_kvs_set,
)
from shelly_mcp.tools.script import (
    shelly_script_create,
    shelly_script_delete,
    shelly_script_eval,
    shelly_script_get_code,
    shelly_script_list,
    shelly_script_put_code,
    shelly_script_start,
)
from shelly_mcp.tools.virtual import (
    shelly_virtual_add,
    shelly_virtual_delete,
    shelly_virtual_list,
)
from shelly_mcp.tools.webhook import (
    shelly_webhook_create,
    shelly_webhook_delete,
    shelly_webhook_list,
    shelly_webhook_update,
)


# ----------------------------------------------------------------------- KVS
async def test_kvs_list(wire: Any) -> None:
    out = await shelly_kvs_list.fn(device="dev")
    assert out["keys"] == {"cfg": "etag1"} and out["rev"] == 3


async def test_kvs_get(wire: Any) -> None:
    out = await shelly_kvs_get.fn(device="dev", key="cfg")
    assert out["value"] == "hello" and out["etag"] == "etag1"


async def test_kvs_set_audited(wire: Any) -> None:
    out = await shelly_kvs_set.fn(device="dev", key="cfg", value={"a": 1})
    assert "set" in out
    assert ("KVS.Set", {"key": "cfg", "value": {"a": 1}}) in wire.calls


async def test_kvs_set_rejects_blank_key(wire: Any) -> None:
    assert "error" in await shelly_kvs_set.fn(device="dev", key="", value=1)


async def test_kvs_delete_confirm_gate(wire: Any) -> None:
    refused = await shelly_kvs_delete.fn(device="dev", key="cfg")
    assert refused["confirmed"] is False
    assert not any(m == "KVS.Delete" for m, _ in wire.calls)
    ok = await shelly_kvs_delete.fn(device="dev", key="cfg", confirm=True)
    assert ok["confirmed"] is True
    assert any(m == "KVS.Delete" for m, _ in wire.calls)


# ------------------------------------------------------------------- Webhook
async def test_webhook_list(wire: Any) -> None:
    out = await shelly_webhook_list.fn(device="dev")
    assert out["hooks"][0]["event"] == "switch.on"


async def test_webhook_create_ok(wire: Any) -> None:
    out = await shelly_webhook_create.fn(
        device="dev", event="switch.on", cid=0, urls=["http://x/y"]
    )
    assert "created" in out
    method, params = next((m, p) for m, p in wire.calls if m == "Webhook.Create")
    assert params["event"] == "switch.on" and params["urls"] == ["http://x/y"]


async def test_webhook_create_rejects_no_urls(wire: Any) -> None:
    out = await shelly_webhook_create.fn(device="dev", event="switch.on", cid=0, urls=[])
    assert "error" in out


async def test_webhook_create_rejects_too_many_urls(wire: Any) -> None:
    out = await shelly_webhook_create.fn(
        device="dev", event="switch.on", cid=0, urls=[f"http://u/{i}" for i in range(6)]
    )
    assert "error" in out and "5 urls" in out["error"]


async def test_webhook_update_partial(wire: Any) -> None:
    await shelly_webhook_update.fn(device="dev", id=1, enable=False)
    _, params = next((m, p) for m, p in wire.calls if m == "Webhook.Update")
    assert params == {"id": 1, "enable": False}


async def test_webhook_delete_confirm_gate(wire: Any) -> None:
    assert (await shelly_webhook_delete.fn(device="dev", id=1))["confirmed"] is False
    ok = await shelly_webhook_delete.fn(device="dev", id=1, confirm=True)
    assert ok["confirmed"] is True


# -------------------------------------------------------------------- Script
async def test_script_list(wire: Any) -> None:
    out = await shelly_script_list.fn(device="dev")
    assert out["scripts"][0]["id"] == 1


async def test_script_get_code_reassembles(wire: Any) -> None:
    out = await shelly_script_get_code.fn(device="dev", id=1)
    assert out["code"] == "let x = 1;"


async def test_script_create_audited(wire: Any) -> None:
    out = await shelly_script_create.fn(device="dev", name="blink")
    assert "created" in out
    assert ("Script.Create", {"name": "blink"}) in wire.calls


async def test_script_put_code_confirm_gate(wire: Any) -> None:
    refused = await shelly_script_put_code.fn(device="dev", id=1, code="print(1)")
    assert refused["confirmed"] is False
    assert not any(m == "Script.PutCode" for m, _ in wire.calls)


async def test_script_put_code_chunks_large_code(wire: Any) -> None:
    big = "x" * 2500  # > 2 chunks of 1024
    out = await shelly_script_put_code.fn(device="dev", id=1, code=big, confirm=True)
    put_calls = [p for m, p in wire.calls if m == "Script.PutCode"]
    assert len(put_calls) == 3  # 1024 + 1024 + 452
    assert put_calls[0]["append"] is False  # first replaces
    assert put_calls[1]["append"] is True  # rest append
    assert out["chunks"] == 3


async def test_script_put_code_rejects_blank(wire: Any) -> None:
    assert "error" in await shelly_script_put_code.fn(device="dev", id=1, code="", confirm=True)


async def test_script_start_stop_audited(wire: Any) -> None:
    await shelly_script_start.fn(device="dev", id=1)
    assert ("Script.Start", {"id": 1}) in wire.calls


async def test_script_eval_confirm_gate(wire: Any) -> None:
    refused = await shelly_script_eval.fn(device="dev", id=1, code="1+1")
    assert refused["confirmed"] is False
    ok = await shelly_script_eval.fn(device="dev", id=1, code="1+1", confirm=True)
    assert ok["confirmed"] is True
    assert any(m == "Script.Eval" for m, _ in wire.calls)


async def test_script_delete_confirm_gate(wire: Any) -> None:
    assert (await shelly_script_delete.fn(device="dev", id=1))["confirmed"] is False
    ok = await shelly_script_delete.fn(device="dev", id=1, confirm=True)
    assert ok["confirmed"] is True


# ------------------------------------------------------------------- Virtual
async def test_virtual_list(wire: Any) -> None:
    out = await shelly_virtual_list.fn(device="dev")
    assert out["components"][0]["key"] == "boolean:200"
    assert ("Shelly.GetComponents", {"dynamic_only": True}) in wire.calls


async def test_virtual_add_audited(wire: Any) -> None:
    out = await shelly_virtual_add.fn(device="dev", type="boolean", config={"name": "flag"})
    assert "added" in out
    _, params = next((m, p) for m, p in wire.calls if m == "Virtual.Add")
    assert params["type"] == "boolean" and params["config"] == {"name": "flag"}


async def test_virtual_add_rejects_blank_type(wire: Any) -> None:
    assert "error" in await shelly_virtual_add.fn(device="dev", type="")


async def test_virtual_delete_validates_key(wire: Any) -> None:
    out = await shelly_virtual_delete.fn(device="dev", key="notakey", confirm=True)
    assert "error" in out


async def test_virtual_delete_confirm_gate(wire: Any) -> None:
    assert (await shelly_virtual_delete.fn(device="dev", key="boolean:200"))["confirmed"] is False
    ok = await shelly_virtual_delete.fn(device="dev", key="boolean:200", confirm=True)
    assert ok["confirmed"] is True
