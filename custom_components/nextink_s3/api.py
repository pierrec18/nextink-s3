"""Origin-restricted async HTTP client with isolated, memory-only cookies."""

import asyncio
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import DOMAIN, MAX_REDIRECTS, MAX_RESPONSE_BYTES, REQUEST_TIMEOUT, STORAGE_URL
from .errors import (
    AccessDeniedError,
    AuthenticationError,
    ConnectionError,
    DataError,
    InteractiveAuthError,
    RateLimitError,
    StructureError,
)
from .parser import (
    Quota,
    check_challenge,
    explicit_rejection,
    has_login,
    parse_login,
    parse_quota,
    safe_url,
)


def retry_seconds(value: str | None) -> float:
    """Honor delta seconds and HTTP dates, with a safe default."""
    if value:
        try:
            return max(1, int(value))
        except ValueError:
            try:
                return max(1, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
            except ValueError, TypeError, OverflowError:
                pass
    return 3600


class NextInkClient:
    """One client per account; one password submission maximum per fetch."""

    def __init__(self, hass: HomeAssistant, username: str, password: str) -> None:
        self._username = username
        self._password = password
        self._session = async_create_clientsession(
            hass,
            cookie_jar=aiohttp.CookieJar(),
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
        )
        self._lock = asyncio.Lock()
        self._auth_blocked = False
        # Preserve server backoff across config-validation/setup/reload clients.
        # Runtime only, never serialized or exposed in diagnostics/entities.
        self._backoffs = hass.data.setdefault(DOMAIN, {})
        self._backoff_key = username.strip().casefold()

    async def async_close(self) -> None:
        """Detach HA's shared connector; discard cookies and references."""
        self._session.cookie_jar.clear()
        self._session.detach()
        self._username = self._password = ""

    async def _request(self, method: str, url: str, data=None) -> tuple[str, str]:
        """Follow redirects manually, validating BEFORE any HTTP request."""
        url = safe_url(url)
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                for _ in range(MAX_REDIRECTS + 1):
                    async with self._session.request(
                        method, url, data=data, allow_redirects=False
                    ) as response:
                        chunks = bytearray()
                        async for chunk in response.content.iter_chunked(16384):
                            chunks.extend(chunk)
                            if len(chunks) > MAX_RESPONSE_BYTES:
                                raise StructureError("response_too_large")
                        html = chunks.decode(response.charset or "utf-8", errors="replace")
                        if response.status == 429:
                            seconds = retry_seconds(response.headers.get("Retry-After"))
                            self._backoffs[self._backoff_key] = time.monotonic() + seconds
                            raise RateLimitError(seconds)
                        if response.status >= 500:
                            raise ConnectionError("server_error")
                        check_challenge(html)
                        if response.status == 403:
                            raise AccessDeniedError("access_denied")
                        if response.status in (301, 302, 303, 307, 308):
                            location = response.headers.get("Location")
                            if not location:
                                raise StructureError("missing_redirect")
                            url = safe_url(location, url)
                            if response.status == 303 or (
                                response.status in (301, 302) and method == "POST"
                            ):
                                method, data = "GET", None
                            continue
                        if response.status >= 400:
                            raise ConnectionError("http_error")
                        if response.status != 200:
                            raise StructureError("unexpected_status")
                        return url, html
                raise StructureError("too_many_redirects")
        except aiohttp.ClientError, TimeoutError, UnicodeError, LookupError:
            raise ConnectionError("cannot_connect") from None

    async def async_fetch(self) -> Quota:
        """Validate success with a complete quota snapshot, never a cookie."""
        async with self._lock:
            if self._auth_blocked:
                raise AuthenticationError("reauth_required")
            retry_at = self._backoffs.get(self._backoff_key, 0.0)
            if time.monotonic() < retry_at:
                raise RateLimitError(retry_at - time.monotonic())
            try:
                page_url, html = await self._request("GET", STORAGE_URL)
                try:
                    return parse_quota(html)
                except DataError:
                    # Only explicit login evidence authorizes password submission.
                    if not has_login(html) and urlsplit(page_url).path.rstrip("/") != "/auth/login":
                        raise
                destination, fields = parse_login(html, page_url)
                fields.update(username=self._username, password=self._password)
                _, result = await self._request("POST", destination, fields)
                if explicit_rejection(result):
                    raise AuthenticationError("invalid_auth")
                # Explicit storage GET is required even after an apparent success.
                _, html = await self._request("GET", STORAGE_URL)
                if explicit_rejection(html):
                    raise AuthenticationError("invalid_auth")
                if has_login(html):
                    raise StructureError("login_result_ambiguous")
                return parse_quota(html)
            except AuthenticationError, InteractiveAuthError:
                self._auth_blocked = True
                raise
