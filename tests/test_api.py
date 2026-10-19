from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from unittest.mock import patch

import pytest
from yarl import URL

from custom_components.nextink_s3.api import NextInkClient, retry_seconds
from custom_components.nextink_s3.const import MAX_REDIRECTS, MAX_RESPONSE_BYTES, STORAGE_URL
from custom_components.nextink_s3.errors import (
    AccessDeniedError,
    AuthenticationError,
    ConnectionError,
    DataError,
    FormError,
    InteractiveAuthError,
    RateLimitError,
    StructureError,
)


class Stream:
    def __init__(self, body):
        self.body = body.encode()

    async def iter_chunked(self, size):
        for offset in range(0, len(self.body), size):
            yield self.body[offset : offset + size]


class Response:
    def __init__(self, body="", status=200, headers=None):
        self.status, self.headers = status, headers or {}
        self.charset, self.content = "utf-8", Stream(body)


def transport(client, responses):
    queue = iter(responses)
    calls = []

    @asynccontextmanager
    async def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        result = next(queue)
        if isinstance(result, Exception):
            raise result
        yield result

    return patch.object(client._session, "request", request), calls


@pytest.fixture
async def client(hass):
    instance = NextInkClient(hass, "synthetic-user", "synthetic-password")
    yield instance
    await instance.async_close()
    assert instance._session.closed


async def test_existing_session(client, quota_html):
    mock, calls = transport(client, [Response(quota_html)])
    with mock:
        assert (await client.async_fetch()).object_count == 16
    assert len(calls) == 1


async def test_login_and_expiration(client, login_html, quota_html):
    responses = [
        Response(quota_html),
        Response(status=302, headers={"Location": "/auth/login/"}),
        Response(login_html),
        Response("apparently successful"),
        Response(quota_html),
    ]
    mock, calls = transport(client, responses)
    with mock:
        await client.async_fetch()
        await client.async_fetch()
    assert [c[0] for c in calls] == ["GET", "GET", "GET", "POST", "GET"]
    assert calls[3][2]["data"]["_wpnonce"] == "synthetic-fresh-nonce"
    assert calls[-1][1] == STORAGE_URL


async def test_quota_missing_never_login(client):
    mock, calls = transport(client, [Response("<h1>Unknown HTML</h1>")])
    with mock, pytest.raises(DataError):
        await client.async_fetch()
    assert len(calls) == 1


async def test_one_attempt_ambiguous_result(client, login_html):
    mock, calls = transport(client, [Response(login_html), Response("OK"), Response(login_html)])
    with mock, pytest.raises(StructureError):
        await client.async_fetch()
    assert sum(c[0] == "POST" for c in calls) == 1


async def test_apparent_success_no_quota(client, login_html):
    mock, calls = transport(
        client, [Response(login_html), Response("OK"), Response("<h1>Profile</h1>")]
    )
    with mock, pytest.raises(DataError):
        await client.async_fetch()
    assert calls[-1][1] == STORAGE_URL


async def test_rejection_stops_future_passwords(client, login_html, caplog):
    mock, calls = transport(
        client,
        [Response(login_html), Response('<div id="login_error">Identifiants incorrects</div>')],
    )
    with mock:
        for _ in range(2):
            with pytest.raises(AuthenticationError):
                await client.async_fetch()
    assert len(calls) == 2
    assert "synthetic-password" not in caplog.text
    assert "synthetic-user" not in caplog.text


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
async def test_external_redirect_rejected(client, status, login_html):
    mock, calls = transport(
        client,
        [
            Response(login_html),
            Response(status=status, headers={"Location": "https://external.test/"}),
        ],
    )
    with mock, pytest.raises(FormError):
        await client.async_fetch()
    assert len(calls) == 2
    assert all(URL(c[1]).host == "next.ink" for c in calls)


async def test_external_form_no_post(client, login_html):
    mock, calls = transport(
        client,
        [
            Response(
                login_html.replace('method="POST"', 'method="POST" action="https://external.test/"')
            )
        ],
    )
    with mock, pytest.raises(FormError):
        await client.async_fetch()
    assert len(calls) == 1


@pytest.mark.parametrize(
    "status,error",
    [
        (403, AccessDeniedError),
        (500, ConnectionError),
        (503, ConnectionError),
        (404, ConnectionError),
    ],
)
async def test_http_errors_no_login(client, status, error):
    mock, calls = transport(client, [Response(status=status)])
    with mock, pytest.raises(error):
        await client.async_fetch()
    assert len(calls) == 1


async def test_rate_limit(client):
    mock, calls = transport(client, [Response(status=429, headers={"Retry-After": "7200"})])
    with mock:
        for _ in range(2):
            with pytest.raises(RateLimitError) as err:
                await client.async_fetch()
            assert err.value.retry_seconds > 7190
    assert len(calls) == 1


async def test_rate_limit_survives_client_reload(hass, client):
    mock, _ = transport(client, [Response(status=429, headers={"Retry-After": "7200"})])
    with mock, pytest.raises(RateLimitError):
        await client.async_fetch()
    other = NextInkClient(hass, "synthetic-user", "synthetic-password")
    try:
        mock, calls = transport(other, [])
        with mock, pytest.raises(RateLimitError):
            await other.async_fetch()
        assert not calls
    finally:
        await other.async_close()


def test_retry_after_date():
    assert 119 <= retry_seconds(format_datetime(datetime.now(UTC) + timedelta(seconds=120))) <= 120
    assert retry_seconds("nonsense") == 3600


async def test_timeout_is_sanitized(client, caplog):
    mock, _ = transport(client, [TimeoutError("synthetic-password")])
    with mock, pytest.raises(ConnectionError, match="cannot_connect"):
        await client.async_fetch()
    assert "synthetic-password" not in caplog.text


async def test_401_with_explicit_rejection(client, login_html):
    mock, _ = transport(
        client,
        [
            Response(login_html),
            Response('<div id="login_error">Incorrect password</div>', status=401),
        ],
    )
    with mock, pytest.raises(AuthenticationError):
        await client.async_fetch()


async def test_401_ambiguous_not_bad_password(client):
    mock, _ = transport(client, [Response("Unknown response", status=401)])
    with mock, pytest.raises(ConnectionError):
        await client.async_fetch()


@pytest.mark.parametrize("body", ['<input name="totp">', '<div class="cf-turnstile"></div>'])
async def test_interactive_blocks_retries(client, body):
    mock, calls = transport(client, [Response(body)])
    with mock:
        with pytest.raises(InteractiveAuthError):
            await client.async_fetch()
        with pytest.raises(AuthenticationError):
            await client.async_fetch()
    assert len(calls) == 1


async def test_cookies_isolated_and_cleared(hass, client):
    other = NextInkClient(hass, "other-synthetic-user", "other-synthetic-password")
    try:
        client._session.cookie_jar.update_cookies({"session": "synthetic-cookie"}, URL(STORAGE_URL))
        assert len(client._session.cookie_jar) == 1
        assert not list(other._session.cookie_jar)
        await client.async_close()
        assert not list(client._session.cookie_jar)
        assert not client._password
    finally:
        await other.async_close()


async def test_too_large(client):
    mock, _ = transport(client, [Response("x" * (MAX_RESPONSE_BYTES + 1))])
    with mock, pytest.raises(StructureError, match="response_too_large"):
        await client.async_fetch()


async def test_redirect_limit(client):
    mock, calls = transport(
        client,
        [Response(status=302, headers={"Location": "/again"}) for _ in range(MAX_REDIRECTS + 1)],
    )
    with mock, pytest.raises(StructureError, match="too_many_redirects"):
        await client.async_fetch()
    assert len(calls) == MAX_REDIRECTS + 1


@pytest.mark.parametrize("status", [307, 308])
async def test_same_origin_preserves_post(client, login_html, quota_html, status):
    mock, calls = transport(
        client,
        [
            Response(login_html),
            Response(status=status, headers={"Location": "/auth/native/"}),
            Response("OK"),
            Response(quota_html),
        ],
    )
    with mock:
        await client.async_fetch()
    assert calls[1][0] == calls[2][0] == "POST"
    assert calls[1][2]["data"] == calls[2][2]["data"]


async def test_new_nonce_each_login(client, login_html, quota_html):
    mock, calls = transport(
        client,
        [
            Response(login_html),
            Response("OK"),
            Response(quota_html),
            Response(login_html.replace("synthetic-fresh-nonce", "synthetic-second-nonce")),
            Response("OK"),
            Response(quota_html),
        ],
    )
    with mock:
        await client.async_fetch()
        await client.async_fetch()
    assert [c[2]["data"]["_wpnonce"] for c in calls if c[0] == "POST"] == [
        "synthetic-fresh-nonce",
        "synthetic-second-nonce",
    ]
