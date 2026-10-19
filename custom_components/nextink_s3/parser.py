"""Strict parsing of displayed estimates, not S3 measurements."""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from .const import ORIGIN
from .errors import DataError, FormError, InteractiveAuthError

LABELS = {
    "Utilisé": "used_bytes",
    "Disponible": "available_bytes",
    "Total": "total_bytes",
    "Objets": "object_count",
}
UNITS = {"o": 1, "B": 1}
for exponent, prefix in enumerate("KMGT", 1):
    UNITS[prefix + "o"] = UNITS[prefix + "B"] = 1000**exponent
    UNITS[prefix + "io"] = UNITS[prefix + "iB"] = 1024**exponent


def normalize(value: str) -> str:
    """Collapse Unicode whitespace, including narrow no-break spaces."""
    return " ".join(value.split())


@dataclass(frozen=True)
class Quota:
    """A complete snapshot of the website's rounded values."""

    used_bytes: Decimal
    available_bytes: Decimal
    total_bytes: Decimal
    object_count: int

    @property
    def percentage(self) -> Decimal | None:
        return self.used_bytes / self.total_bytes * 100 if self.total_bytes else None


def parse_size(value: str) -> Decimal:
    """Read decimal and binary units without binary floating-point rounding."""
    match = re.fullmatch(r"([0-9]+(?: [0-9]{3})*(?:[.,][0-9]+)?)\s*([A-Za-z]+)", normalize(value))
    if not match or match[2] not in UNITS:
        raise DataError("invalid_size")
    try:
        return Decimal(match[1].replace(" ", "").replace(",", ".")) * UNITS[match[2]]
    except InvalidOperation:
        raise DataError("invalid_size") from None


def parse_quota(html: str) -> Quota:
    """Only trust labels inside the exact quota section."""
    soup = BeautifulSoup(html, "html.parser")
    roots = soup.select(".next-s3-quota-usage")
    if len(roots) != 1:
        raise DataError("missing_or_ambiguous_quota")
    values = {}
    for item in roots[0].select(".quota-stats .stat-item"):
        labels, texts = item.select(".stat-label"), item.select(".stat-value")
        if len(labels) != 1 or len(texts) != 1:
            raise DataError("ambiguous_stat")
        label = normalize(labels[0].get_text(" ", strip=True))
        if label not in LABELS:
            continue
        key = LABELS[label]
        if key in values:
            raise DataError("duplicate_stat")
        text = normalize(texts[0].get_text(" ", strip=True))
        if key == "object_count":
            if not re.fullmatch(r"[0-9]+(?: [0-9]{3})*", text):
                raise DataError("invalid_objects")
            values[key] = int(text.replace(" ", ""))
        else:
            values[key] = parse_size(text)
    if set(values) != set(LABELS.values()):
        raise DataError("incomplete_quota")
    return Quota(**values)


def safe_url(value: str, base: str = ORIGIN) -> str:
    """Reject non-canonical origins before a request, including redirect POSTs."""
    try:
        result = urljoin(base, value)
        url = urlsplit(result)
        if (
            url.scheme != "https"
            or url.hostname != "next.ink"
            or url.port not in (None, 443)
            or url.username is not None
            or url.password is not None
            or "\\" in result
            or any(ord(c) < 33 for c in result)
        ):
            raise ValueError
        return result
    except ValueError:
        raise FormError("unsafe_destination") from None


def check_challenge(html: str) -> None:
    """Detect explicit active controls, not incidental script/library names."""
    soup = BeautifulSoup(html, "html.parser")
    if soup.select_one(
        ".g-recaptcha, .h-captcha, .cf-turnstile, #challenge-form, "
        'input[autocomplete="one-time-code"], input[name="otp"], '
        'input[name="totp"], input[name="two_factor_code"], iframe[src*="captcha"]'
    ):
        raise InteractiveAuthError("interactive_auth")
    text = normalize(soup.get_text(" ", strip=True)).casefold()
    if any(
        term in text
        for term in (
            "verify you are human",
            "vérifiez que vous êtes humain",
            "verification required",
            "saisissez votre code de vérification",
            "enter your authentication code",
        )
    ):
        raise InteractiveAuthError("interactive_auth")


def has_login(html: str) -> bool:
    return BeautifulSoup(html, "html.parser").select_one("form#loginForm") is not None


def explicit_rejection(html: str) -> bool:
    """Only classify clear errors in error containers, never arbitrary prose."""
    soup = BeautifulSoup(html, "html.parser")
    errors = soup.select(
        '#login_error, .login-error, .error-message, [role="alert"], [data-testid="login-error"]'
    )
    return any(
        any(
            term in normalize(node.get_text(" ", strip=True)).casefold()
            for term in (
                "mot de passe incorrect",
                "identifiants incorrect",
                "identifiants invalid",
                "incorrect password",
                "invalid credentials",
                "unknown username",
                "utilisateur inconnu",
            )
        )
        for node in errors
    )


def parse_login(html: str, page_url: str) -> tuple[str, dict[str, str]]:
    """Extract a fresh native form, with no hardcoded nonce."""
    check_challenge(html)
    soup = BeautifulSoup(html, "html.parser")
    forms = soup.select("form#loginForm")
    if len(forms) != 1:
        raise FormError("missing_login_form")
    form = forms[0]
    if str(form.get("method", "get")).casefold() != "post":
        raise FormError("unsupported_method")
    if soup.find("base"):
        raise FormError("unsupported_base_url")
    destination = safe_url(str(form.get("action", "")), page_url)
    fields = {}
    for node in form.select('input[type="hidden"][name]'):
        name = str(node["name"])
        if name in fields or name in ("username", "password", "submit"):
            raise FormError("ambiguous_fields")
        fields[name] = str(node.get("value", ""))
    if not fields.get("_wpnonce") or fields.get("bifrost_auth_action") != "login":
        raise FormError("unsupported_fields")
    for name, kind in (("username", "text"), ("password", "password")):
        nodes = form.select(f'input[name="{name}"]')
        if len(nodes) != 1 or nodes[0].get("type") not in (
            {kind, "email"} if name == "username" else {kind}
        ):
            raise FormError("unsupported_fields")
    buttons = form.select('[name="submit"][type="submit"]')
    if len(buttons) != 1 or buttons[0].has_attr("formaction") or buttons[0].has_attr("formmethod"):
        raise FormError("unsupported_submit")
    fields["submit"] = str(buttons[0].get("value", "Connexion"))
    return destination, fields
