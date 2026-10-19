from decimal import Decimal

import pytest

from custom_components.nextink_s3.errors import DataError, FormError, InteractiveAuthError
from custom_components.nextink_s3.parser import parse_login, parse_quota, parse_size, safe_url


def test_example(quota_html):
    data = parse_quota(quota_html)
    assert data.used_bytes == 0
    assert data.available_bytes == data.total_bytes == Decimal("1.98") * 1024**4
    assert data.object_count == 16
    assert data.percentage == 0


@pytest.mark.parametrize(
    "unit,factor",
    [
        ("o", 1),
        ("B", 1),
        ("Ko", 1000),
        ("KB", 1000),
        ("Kio", 1024),
        ("KiB", 1024),
        ("Mo", 1000**2),
        ("MB", 1000**2),
        ("Mio", 1024**2),
        ("MiB", 1024**2),
        ("Go", 1000**3),
        ("GB", 1000**3),
        ("Gio", 1024**3),
        ("GiB", 1024**3),
        ("To", 1000**4),
        ("TB", 1000**4),
        ("Tio", 1024**4),
        ("TiB", 1024**4),
    ],
)
def test_units(unit, factor):
    assert parse_size(f"1,98 {unit}") == Decimal("1.98") * factor


@pytest.mark.parametrize(
    "value", ["", "Indisponible", "-1 Go", "NaN B", "1 XB", "1.2.3 B", "12 34 B", "∞ B"]
)
def test_invalid_sizes(value):
    with pytest.raises(DataError):
        parse_size(value)


def test_spaces_nested_order_and_outside(quota_html):
    html = quota_html.replace("Utilisé", "  Utilisé\u00a0").replace("0 Tio", "<b>1,2</b>\u202fGio")
    html = html.replace("16</span>", "1\u00a0234</span>")
    # Reverse stat items without affecting scope.
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one(".quota-stats")
    items = list(root.select(".stat-item"))
    for item in items[::-1]:
        root.append(item.extract())
    data = parse_quota(
        str(soup)
        + '<div class="stat-item"><b class="stat-label">Total</b><b class="stat-value">99 Go</b></div>'
    )
    assert data.used_bytes == Decimal("1.2") * 1024**3
    assert data.object_count == 1234


@pytest.mark.parametrize(
    "old,new",
    [
        ("0 Tio", "Indisponible"),
        ("0 Tio", ""),
        ("Utilisé", "Absent"),
        ("16</span>", "-1</span>"),
        ("16</span>", "1,6</span>"),
    ],
)
def test_invalid_snapshot(quota_html, old, new):
    with pytest.raises(DataError):
        parse_quota(quota_html.replace(old, new))


def test_duplicates(quota_html):
    with pytest.raises(DataError):
        parse_quota(quota_html.replace("Disponible", "Utilisé"))
    with pytest.raises(DataError):
        parse_quota(quota_html + quota_html)


def test_zero_total_and_rounding(quota_html):
    assert parse_quota(quota_html.replace("1.98 Tio", "0 B")).percentage is None
    data = parse_quota(quota_html.replace("0 Tio", "1.01 Tio").replace("1.98 Tio", "1 Tio"))
    assert data.percentage == 101  # No artificial clamp or exact sum constraint.


@pytest.mark.parametrize(
    "action", ["", ' action="/auth/login/"', ' action="https://next.ink/auth/login/"']
)
def test_fresh_form(login_html, action):
    url, fields = parse_login(
        login_html.replace('id="loginForm"', 'id="loginForm"' + action),
        "https://next.ink/auth/login/",
    )
    assert url == "https://next.ink/auth/login/"
    assert fields["_wpnonce"] == "synthetic-fresh-nonce"
    assert fields["bifrost_auth_action"] == "login"


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.test/",
        "http://next.ink/",
        "https://next.ink:444/",
        "https://a@next.ink/",
        "//evil.test/",
        "https://next.ink.evil.test",
        "https://next.ink\\@evil.test/",
    ],
)
def test_unsafe_urls(url, login_html):
    with pytest.raises(FormError):
        safe_url(url)
    with pytest.raises(FormError):
        parse_login(
            login_html.replace('method="POST"', f'method="POST" action="{url}"'),
            "https://next.ink/auth/login/",
        )


@pytest.mark.parametrize("change", ['method="GET"', 'method="POST" action="https://evil.test"'])
def test_bad_form(login_html, change):
    with pytest.raises(FormError):
        parse_login(login_html.replace('method="POST"', change), "https://next.ink/auth/login/")


@pytest.mark.parametrize(
    "challenge",
    [
        '<div class="g-recaptcha"></div>',
        '<input name="totp">',
        '<input autocomplete="one-time-code">',
        '<form id="challenge-form"></form>',
    ],
)
def test_challenge(login_html, challenge):
    with pytest.raises(InteractiveAuthError):
        parse_login(login_html + challenge, "https://next.ink/auth/login/")


@pytest.mark.parametrize(
    "value,expected",
    [("1,632", 1632), ("12,345,678", 12345678), ("0", 0), ("1 632", 1632), ("1632", 1632)],
)
def test_object_count_grouping(quota_html, value, expected):
    assert parse_quota(quota_html.replace("16</span>", f"{value}</span>")).object_count == expected


@pytest.mark.parametrize(
    "value", ["1,63", "1,632,00", "1,632 000", "1234,567", "1.632", "1,6", "-1", "1k"]
)
def test_invalid_object_grouping(quota_html, value):
    with pytest.raises(DataError, match="invalid_objects"):
        parse_quota(quota_html.replace("16</span>", f"{value}</span>"))
