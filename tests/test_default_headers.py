"""Contract tests for client-level default headers (slice 016 §1.1).

The MCP process must be attributable on EVERY call, not just the one lane that
happened to send the header first. These tests assert the wire behaviour: the
header survives GET, POST and the 401-refresh retry, per-call values win over
the default, and ``Authorization`` is never overridable.
"""

import unittest
from unittest.mock import AsyncMock, patch

import httpx

from geopack_sdk import GeopackClient
from geopack_sdk.async_client import AsyncGeopackClient

_MCP = {"X-Geoportal-Client": "mcp"}


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.ok = status_code < 400
        self.content = b"{}"
        self.text = "{}"
        self.reason = "OK" if self.ok else "Unauthorized"

    def json(self):
        return self._payload


def _effective_headers(client, call):
    """Emulate ``requests`` merging: session headers, then per-call headers."""
    merged = dict(client.session.headers)
    merged.update(call.kwargs.get("headers") or {})
    return merged


class SyncDefaultHeadersTest(unittest.TestCase):
    def setUp(self):
        self.client = GeopackClient(
            "http://example.test/api",
            default_headers=dict(_MCP),
            enable_http_retries=False,
        )
        self.client.auth.token = "tok"

    def _call(self, method, *args, **kwargs):
        with patch.object(
            self.client.session, "request", return_value=_FakeResponse()
        ) as request:
            getattr(self.client, method)(*args, **kwargs)
        return _effective_headers(self.client, request.call_args)

    def test_header_present_on_get_and_post(self):
        get_headers = self._call("get", "/datasets")
        post_headers = self._call("post", "/datasets", json={"name": "x"})

        for headers in (get_headers, post_headers):
            self.assertEqual(headers["X-Geoportal-Client"], "mcp")
            self.assertEqual(headers["Authorization"], "Bearer tok")

    def test_per_call_headers_win_over_defaults(self):
        headers = self._call(
            "get",
            "/datasets",
            headers={"X-Geoportal-Client": "cli", "X-Trace": "trace-1"},
        )

        self.assertEqual(headers["X-Geoportal-Client"], "cli")
        self.assertEqual(headers["X-Trace"], "trace-1")

    def test_authorization_is_never_overridable(self):
        headers = self._call(
            "get", "/datasets", headers={"Authorization": "Bearer attacker"}
        )

        self.assertEqual(headers["Authorization"], "Bearer tok")

    def test_401_refresh_retries_with_the_same_headers(self):
        self.client.auth.refresh_token = "refresh-1"
        responses = [_FakeResponse(401), _FakeResponse(200, {"ok": True})]

        with patch.object(
            self.client.session, "request", side_effect=responses
        ) as request, patch.object(
            self.client.auth, "refresh", side_effect=lambda *a, **k: None
        ):
            self.assertEqual(self.client.get("/datasets"), {"ok": True})

        self.assertEqual(request.call_count, 2)
        for call in request.call_args_list:
            self.assertEqual(call.kwargs["headers"]["X-Geoportal-Client"], "mcp")


class AsyncDefaultHeadersTest(unittest.IsolatedAsyncioTestCase):
    def _client(self, handler):
        client = AsyncGeopackClient(
            "http://example.test/api",
            default_headers=dict(_MCP),
            enable_http_retries=False,
        )
        # Replace the transport so no socket is opened; headers still travel.
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client.auth.token = "tok"
        return client

    async def test_header_present_on_get_and_post(self):
        seen = []

        def handler(request):
            seen.append(request.headers)
            return httpx.Response(200, json={})

        client = self._client(handler)
        try:
            await client.get("/datasets")
            await client.post("/datasets", json={"name": "x"})
        finally:
            await client.aclose()

        self.assertEqual(len(seen), 2)
        for headers in seen:
            self.assertEqual(headers["x-geoportal-client"], "mcp")
            self.assertEqual(headers["authorization"], "Bearer tok")

    async def test_401_refresh_retries_with_the_same_headers(self):
        seen = []

        def handler(request):
            seen.append(request.headers)
            status = 401 if len(seen) == 1 else 200
            return httpx.Response(status, json={})

        client = self._client(handler)
        client.auth.refresh_token = "refresh-1"
        try:
            with patch.object(client.auth, "refresh", new=AsyncMock()) as refresh:
                self.assertEqual(await client.get("/datasets"), {})
            refresh.assert_awaited_once()
        finally:
            await client.aclose()

        self.assertEqual(len(seen), 2)
        for headers in seen:
            self.assertEqual(headers["x-geoportal-client"], "mcp")


if __name__ == "__main__":
    unittest.main()
