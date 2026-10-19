# Validation report — 2026-10-19

## Target and evidence

- Live instance inspected using HA's system-health API: **Home Assistant OS 18.3**,
  **Core 2026.10.2**, Python **3.14.6**, HACS **2.0.5**, healthy/supported.
- Official Core 2026.10.2 `pyproject.toml`: **requires-python >=3.14.2**.
- Isolated test environment: CPython **3.14.8**, **homeassistant==2026.10.2**,
  **pytest-homeassistant-custom-component==0.13.373**.
- Public native Next.ink form inspected with GET only on 2026-10-19. It contains
  `loginForm`, POST, fresh nonce and native username/password fields.
- No alternative existing Next.ink S3 integration was found in a targeted GitHub,
  web and HACS search. This is not a claim of exhaustive global search.
- Current HACS publishing requirements checked at
  https://www.hacs.xyz/docs/publish/integration/ (manifest, single integration,
  documentation and brand assets). Local `brand/icon.png` is supplied. This custom
  repository is **not submitted to the default catalogue**. The legacy HACS brands
  catalogue check is ignored in CI; local brand assets are provided instead.

## Automated validation

The suite runs against real Home Assistant APIs with **synthetic HTTP responses**
and network sockets disabled by pytest. It does not verify a production login.

Covered:

- French/English decimal and binary units, Decimal conversion, Unicode whitespace,
  nested tags, reordered statistics, exact quota scope, missing/unavailable values,
  duplicates, invalid sizes/object counts, zero total, independent rounding and
  percentages over 100 without clamping.
- Fresh form nonce and hidden fields; absent/relative/absolute actions; external
  form and redirect rejection including 307/308; supported internal 307/308 body
  preservation; bounded redirects and decompressed response size.
- Successful quota read; session loss followed by one controlled login; changed
  nonce; explicit credential rejection with retry blocking; ambiguous responses;
  apparently successful login without quota; no login on missing quota alone.
- Explicit interactive challenges; 403/429/5xx/timeouts; Retry-After seconds/date,
  no premature retry, including a replacement client after reload.
- Isolated cookie jars, cleanup on validation/setup failure, cancellation and
  unload. Sanitized network errors and absence of synthetic secrets in logs.
- Entry creation only after validation; translated error mappings; obvious duplicate
  prevention; standard reauth updates the same entry; options without password.
- Six real HA sensor entities on one device, stable IDs across reload; shared
  coordinator; temporary unavailability and recovery; retained last-success timestamp;
  options-triggered reload and cleanup.

Local result: **95 tests passed, 95% statement coverage** (373 statements, 17 not covered),
with BeautifulSoup **4.13.3** aligned with Home Assistant constraints. Syntax,
Ruff, HACS action and hassfest are separate checks from the unit/integration suite.

## Live verification — not yet completed

The following must not be inferred from simulated tests:

| Verification | Status |
|---|---|
| Current HA/Core/HACS version inspected | Passed |
| Public native form reachable from development host | Passed (GET only) |
| HACS custom repository registration | Passed: integration category, correct config path |
| HACS download | Pending deployment |
| Core restart and integration discovery | Pending deployment |
| Next.ink access from HA network | Pending |
| Native account login through local HA form | Pending user credential entry |
| Authenticated quota markup / sensor comparison | Pending account configuration |
| Restart with configured account | Pending |
| Controlled in-memory cookie loss and successful reconnect | Pending |
| Live unavailable/recovery after simulated network failure | Pending |
| Unload/reload of configured production entry | Pending |
| Natural session expiration / cookie lifetime | Not observed |
| Account-specific CAPTCHA/2FA and LPL-only behavior | Not validated |

No fabricated credentials were sent to Next.ink. No production HTML, cookies,
passwords or S3 keys are included in this repository or fixtures. Real credentials
must be entered locally in Home Assistant, not in this chat or GitHub.

## Reproduction and rollback

See README.md for exact commands, HACS/manual install, uninstall and rollback.
Clearing cookies (if subsequently tested) validates recovery after **session loss**,
not natural expiration or a measured session lifetime. Never change the real account
password or disable 2FA to trigger a test. Never deliberately disrupt the whole HA
instance's network to simulate a single integration failure.
