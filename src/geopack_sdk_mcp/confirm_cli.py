"""Operator CLI for human approval of destructive MCP operations."""

from __future__ import annotations

import argparse
import json
import sys

from .confirmation import get_confirmation_manager


def _print_json(data: object) -> None:
    print(json.dumps(data, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="geopack-sdk-confirm",
        description=(
            "Approve or reject destructive Geopack MCP operations. "
            "This CLI is for humans/operators only — not exposed to LLM agents."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List pending confirmation requests")

    status_p = sub.add_parser("status", help="Show one confirmation by ID")
    status_p.add_argument("confirmation_id")

    approve_p = sub.add_parser("approve", help="Approve a pending confirmation")
    approve_p.add_argument("confirmation_id")
    approve_p.add_argument(
        "--by",
        default="operator",
        help="Operator identity recorded in the audit log",
    )

    reject_p = sub.add_parser("reject", help="Reject a pending confirmation")
    reject_p.add_argument("confirmation_id")
    reject_p.add_argument("--reason", default="User rejected")

    sub.add_parser("cleanup", help="Remove expired confirmations from the store")

    args = parser.parse_args(argv)
    manager = get_confirmation_manager()

    if args.command == "list":
        pending = manager.list_pending()
        _print_json(
            {
                "count": len(pending),
                "confirmations": [req.to_dict() for req in pending],
            }
        )
        return 0

    if args.command == "status":
        req = manager.get_request(args.confirmation_id)
        if req is None:
            print("Confirmation not found or expired.", file=sys.stderr)
            return 1
        _print_json(req.to_dict())
        return 0

    if args.command == "approve":
        ok = manager.approve_request(args.confirmation_id, approved_by=args.by)
        if not ok:
            print(
                "Could not approve (not found, expired, or not pending).",
                file=sys.stderr,
            )
            return 1
        req = manager.get_request(args.confirmation_id)
        _print_json(
            {
                "success": True,
                "message": (
                    f"Approved. Agent may execute with confirmation_id={args.confirmation_id}"
                ),
                "confirmation": req.to_dict() if req else None,
            }
        )
        return 0

    if args.command == "reject":
        ok = manager.reject_request(args.confirmation_id, reason=args.reason)
        if not ok:
            print(
                "Could not reject (not found, expired, or not pending).",
                file=sys.stderr,
            )
            return 1
        _print_json(
            {
                "success": True,
                "message": f"Rejected: {args.reason}",
                "confirmation_id": args.confirmation_id,
            }
        )
        return 0

    if args.command == "cleanup":
        removed = manager.cleanup_expired()
        _print_json({"success": True, "removed_count": removed})
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
