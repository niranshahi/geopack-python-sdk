"""Demonstration of the confirmation workflow (no MCP server required)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from geopack_sdk_mcp.confirmation import ConfirmationManager
from geopack_sdk_mcp.destructive_guard import guard_destructive_operation


def test_confirmation_flow() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp) / "confirmations.json"
        os.environ["GEOPACK_CONFIRM_STORE"] = str(store)
        manager = ConfirmationManager(store_path=store)

        print("\n[Agent] delete_dataset(2429) — first call creates pending request")
        guard = guard_destructive_operation("delete_dataset", 2429)
        print(guard.response)

        cid = guard.confirmation_id
        assert cid

        print("\n[Human] geopack-sdk-confirm approve", cid)
        manager.approve_request(cid, approved_by="operator")

        print("\n[Agent] delete_dataset(2429, confirmation_id=...) — may execute")
        ready = guard_destructive_operation(
            "delete_dataset", 2429, confirmation_id=cid
        )
        print("should_execute:", ready.should_execute)

        manager.consume_request(cid)
        print("\n[Agent] second execute with same id — blocked (single-use)")
        reused = guard_destructive_operation(
            "delete_dataset", 2429, confirmation_id=cid
        )
        print(reused.response)

        os.environ.pop("GEOPACK_CONFIRM_STORE", None)


if __name__ == "__main__":
    test_confirmation_flow()
