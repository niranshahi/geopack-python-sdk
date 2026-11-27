"""``geopack-sdk`` CLI — login, logout, status and profile management (slice 034).

The CLI is the only place a password is accepted. It persists the refresh token
through a :class:`~geopack_sdk.credentials.CredentialStore` (OS keyring by
default) and records non-secret profile metadata; the SDK/MCP then run on the
stored session without a password.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from geopack_sdk import GeopackClient
from geopack_sdk.auth_state import store_key
from geopack_sdk.credentials import (
    CredentialStoreError,
    ProfileRegistry,
    StoredCredentials,
    StoredProfile,
    clear_credentials,
    credentials_file_path,
    resolve_store,
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


def _profile(args: argparse.Namespace) -> str:
    return getattr(args, "profile", None) or os.getenv("GEOPACK_PROFILE") or "default"


def cmd_login(args: argparse.Namespace) -> int:
    api_url = args.api_url or _api_url_from_env()
    username = args.username or os.getenv("GEOPACK_USERNAME")
    if not username:
        username = input("Username: ").strip()
    password = args.password or os.getenv("GEOPACK_PASSWORD")
    if not password:
        password = getpass.getpass("Password: ")

    profile = _profile(args)
    try:
        store = resolve_store(args.store)
    except CredentialStoreError as exc:
        print(f"Cannot store credentials: {exc}", file=sys.stderr)
        return 1

    client = GeopackClient(
        base_url=api_url, credential_store=store, auth_profile=profile
    )
    response = client.auth.login(username=username, password=password)
    if not client.auth.token:
        print("Login failed: no access token in response.", file=sys.stderr)
        return 1

    resolved_user = (
        (response.get("user") or {}).get("userName") if isinstance(response, dict) else None
    ) or username

    # Refresh token is already persisted write-through by AuthState.login (D4).
    ProfileRegistry().upsert(
        StoredProfile(
            profile=profile,
            api_url=api_url,
            username=resolved_user,
            store=store.name,
        )
    )
    # Keep the legacy single-file credential in sync so a not-yet-migrated MCP
    # host still works until P4 lands.
    save_credentials(
        StoredCredentials(
            api_url=api_url,
            access_token=client.auth.token,
            refresh_token=client.auth.refresh_token,
            username=resolved_user,
        )
    )

    print(f"Logged in as {resolved_user} (profile '{profile}', store '{store.name}').")
    print("Configure MCP with GEOPACK_API_URL only (no password in mcp.json).")
    return 0


def _best_effort_revoke(entry: StoredProfile, store) -> None:
    """Revoke the profile's server session if the API is reachable (D9)."""
    key = store_key(entry.api_url, entry.profile)
    refresh = store.get_refresh_token(key)
    if not refresh:
        return
    try:
        client = GeopackClient(
            base_url=entry.api_url, credential_store=store, auth_profile=entry.profile
        )
        client.auth.refresh_token = refresh
        try:
            client.auth.refresh()  # mint an access token (rotation is persisted)
        except Exception:
            pass
        try:
            client.post("/auth/logout")
        except Exception:
            print(
                f"Note: could not revoke the server session for '{entry.profile}' "
                "(the portal may not expose POST /auth/logout yet); it may still be active.",
                file=sys.stderr,
            )
    except Exception as exc:  # pragma: no cover - network dependent
        print(f"Note: server revoke skipped for '{entry.profile}': {exc}", file=sys.stderr)


def cmd_logout(args: argparse.Namespace) -> int:
    registry = ProfileRegistry()
    if args.all:
        targets = list(registry.load().values())
    else:
        profile = _profile(args)
        entry = registry.get(profile)
        targets = [entry] if entry else []

    if not targets:
        print("No saved profile to log out.")
        clear_credentials()
        return 0

    for entry in targets:
        try:
            store = resolve_store(entry.store)
        except CredentialStoreError as exc:
            print(f"Warning: {exc}", file=sys.stderr)
            registry.remove(entry.profile)
            continue
        _best_effort_revoke(entry, store)
        store.delete_refresh_token(store_key(entry.api_url, entry.profile))
        registry.remove(entry.profile)
        print(f"Logged out '{entry.profile}'.")

    clear_credentials()
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    registry = ProfileRegistry()
    profile = _profile(args)
    entry = registry.get(profile)
    if not entry:
        print(f"Not logged in (no profile '{profile}').")
        return 1

    try:
        store = resolve_store(entry.store)
        has_refresh = bool(store.get_refresh_token(store_key(entry.api_url, entry.profile)))
    except CredentialStoreError:
        has_refresh = False

    print(f"Profile:  {entry.profile}")
    print(f"API URL:  {entry.api_url}")
    print(f"User:     {entry.username or '(unknown)'}")
    print(f"Store:    {entry.store}")
    print(f"Session:  {'refresh token present' if has_refresh else 'no refresh token'}")
    return 0


def cmd_profiles(_args: argparse.Namespace) -> int:
    registry = ProfileRegistry()
    entries = registry.load()
    if not entries:
        print("No saved profiles.")
        return 0
    for name in sorted(entries):
        entry = entries[name]
        print(f"{name}\t{entry.api_url}\t{entry.username or ''}\t{entry.store}")
    return 0


def main(argv=None) -> int:
    load_geopack_env()

    parser = argparse.ArgumentParser(
        prog="geopack-sdk",
        description="Geopack Python SDK utilities",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    login_p = sub.add_parser("login", help="Log in and persist a session")
    login_p.add_argument("--api-url", dest="api_url", help="Override GEOPACK_API_URL")
    login_p.add_argument("--username", help="Override GEOPACK_USERNAME")
    login_p.add_argument("--password", help="Override GEOPACK_PASSWORD (discouraged)")
    login_p.add_argument("--profile", help="Profile name (default: 'default')")
    login_p.add_argument("--store", help="Credential store: keyring | file | memory")
    login_p.set_defaults(func=cmd_login)

    logout_p = sub.add_parser("logout", help="Revoke the session and clear local credentials")
    logout_p.add_argument("--profile", help="Profile name (default: 'default')")
    logout_p.add_argument("--all", action="store_true", help="Log out every stored profile")
    logout_p.set_defaults(func=cmd_logout)

    status_p = sub.add_parser("status", help="Show the stored session summary")
    status_p.add_argument("--profile", help="Profile name (default: 'default')")
    status_p.set_defaults(func=cmd_status)

    profiles_p = sub.add_parser("profiles", help="List stored profiles")
    profiles_p.set_defaults(func=cmd_profiles)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
