"""``geopack-sdk`` CLI — login, logout, and credential status."""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from geopack_sdk import GeopackClient
from geopack_sdk.credentials import (
    StoredCredentials,
    clear_credentials,
    credentials_file_path,
    load_credentials,
    save_credentials,
)
from geopack_sdk.env_loader import load_geopack_env


def _api_url_from_env() -> str:
    url = os.getenv("GEOPACK_API_URL")
    if not url:
        raise SystemExit(
            "GEOPACK_API_URL is required (e.g. http://localhost:3000/api). "
            "Set it in the environment or python-sdk/.env before running geopack-sdk login."
        )
    return url


def cmd_login(args: argparse.Namespace) -> int:
    api_url = args.api_url or _api_url_from_env()
    username = args.username or os.getenv("GEOPACK_USERNAME")
    if not username:
        username = input("Username: ").strip()
    password = args.password or os.getenv("GEOPACK_PASSWORD")
    if not password:
        password = getpass.getpass("Password: ")

    os.environ["GEOPACK_API_URL"] = api_url
    client = GeopackClient(base_url=api_url)
    response = client.auth.login(username=username, password=password)
    if not client.auth.token:
        print("Login failed: no access token in response.", file=sys.stderr)
        return 1

    path = save_credentials(
        StoredCredentials(
            api_url=api_url,
            access_token=client.auth.token,
            refresh_token=client.auth.refresh_token,
            username=response.get("user", {}).get("userName") or username,
        )
    )
    print(f"Logged in as {username}. Tokens saved to {path}")
    print("Configure MCP with GEOPACK_API_URL only (no password in mcp.json).")
    return 0


def cmd_logout(_args: argparse.Namespace) -> int:
    if clear_credentials():
        print(f"Removed {credentials_file_path()}")
    else:
        print("No saved credentials.")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    api_url = args.api_url or os.getenv("GEOPACK_API_URL")
    creds = load_credentials(api_url=api_url) if api_url else load_credentials()
    if not creds:
        print("Not logged in (no matching credentials file).")
        return 1
    print(f"API URL:  {creds.api_url}")
    print(f"User:     {creds.username or '(unknown)'}")
    print(f"Token:    {creds.access_token[:12]}…")
    print(f"File:     {credentials_file_path()}")
    return 0


def main(argv=None) -> int:
    load_geopack_env()

    parser = argparse.ArgumentParser(
        prog="geopack-sdk",
        description="Geopack Python SDK utilities",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    login_p = sub.add_parser("login", help="Save JWT tokens to ~/.geopack/credentials.json")
    login_p.add_argument("--api-url", dest="api_url", help="Override GEOPACK_API_URL")
    login_p.add_argument("--username", help="Override GEOPACK_USERNAME")
    login_p.add_argument("--password", help="Override GEOPACK_PASSWORD (discouraged)")
    login_p.set_defaults(func=cmd_login)

    logout_p = sub.add_parser("logout", help="Remove saved credentials")
    logout_p.set_defaults(func=cmd_logout)

    status_p = sub.add_parser("status", help="Show saved credential summary")
    status_p.add_argument("--api-url", dest="api_url", help="Match stored API URL")
    status_p.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
