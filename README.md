# Next.ink S3 for Home Assistant

![Next.ink](custom_components/nextink_s3/brand/logo.png)

Read-only monitoring of the **rounded storage quota displayed by Next.ink**.
Unofficial integration; no affiliation with Next.ink, HACS or Home Assistant.

Requires **Home Assistant 2026.10.0+**. Developed and tested against Core
2026.10.2 / Python 3.14. No S3 keys, bucket listing, object access or mutations.

## Sensors

Used storage, available storage and total quota (native bytes; displayed as GiB),
object count, percentage used, and a diagnostic last-success timestamp.
All five measurements become unavailable if any required statistic is invalid.
The diagnostic timestamp remains available after a failed refresh, so stale data
can be identified. It is a runtime timestamp, not restored across HA restarts.
The first successful startup read sets it again.

**These are estimates, not byte-accurate S3 measurements.** For example, `0 Tio`
can hide small nonzero usage. Decimal `To` and binary `Tio` are distinct.
Rounded used and available values need not sum exactly to total. A zero total
makes the percentage unknown; percentages are never artificially clamped.

## HACS custom repository installation

1. In HACS → ⋮ → Custom repositories, add
   `https://github.com/pierrec18/nextink-s3`, category **Integration**.
2. Find **Next.ink S3** and download the desired release.
3. Restart Home Assistant.
4. Settings → Devices & services → Add integration → **Next.ink S3**.
5. Enter native Next.ink username/email and password **locally in HA**.
6. Check the six entities against the storage page.

[Open the integration setup](https://my.home-assistant.io/redirect/config_flow_start/?domain=nextink_s3)

This is installation through a **custom** repository, not inclusion in the HACS
default catalogue or an official HACS endorsement. See [VALIDATION.md](VALIDATION.md)
for the actual automated and live verification status.

## Manual installation

Extract the release archive so this directory exists:

```text
/config/custom_components/nextink_s3/manifest.json
```

Do not nest `custom_components` twice. On Home Assistant Container, first inspect
the running container's mounts and identify the host directory actually mapped to
`/config`; never assume a host path. Restart and follow steps 4–6 above.

## Authentication and privacy

Only the native Next.ink login form is supported. LPL-only accounts, CAPTCHA and
interactive two-factor challenges are unsupported. Do not disable 2FA.
Credentials are stored using normal HA config entries: **not a dedicated encrypted
vault**. Someone with access to configuration files or backups may read them.
Protect HA and its backups. Session cookies stay in memory and are isolated per
account. No HTML, cookies, credentials or telemetry are exported by this integration.

See [AUTHENTICATION.md](AUTHENTICATION.md) for the security model and limitations.

## Polling, options and troubleshooting

Default: every six hours. Use the integration's **Configure** button to choose
1–24 hours without entering the password. A single request cycle serves all sensors.

- Explicit credential rejection: follow Home Assistant's standard reauthentication
  flow. The entry and entity IDs remain unchanged.
- Interactive challenge: automatic authentication is unsupported in that state;
  retries stop and reauthentication is requested. Do not disable account protections.
- 403: access denied or protection; **not** evidence of a wrong password.
- 429: `Retry-After` is honored; no immediate login retry.
- Network/5xx: temporary unavailability; no fake zero values.
- Missing quota, unavailable value or unknown HTML: compatibility/data error.
  The client does not resubmit passwords just because quota markup is absent.
- Identical login names (case-insensitive) cannot be configured twice. Without a
  verified public account ID, a username and email alias for the same account
  cannot reliably be deduplicated. Keep one entry per account.

Report sanitized issues at https://github.com/pierrec18/nextink-s3/issues.
Never attach a password, cookie, authenticated page or unredacted HA backup.

## Uninstall / rollback

Remove the integration entry in Settings → Devices & services first, then remove
the download in HACS and restart. For manual installs, remove only
`/config/custom_components/nextink_s3/` after unloading the entry. Existing recorder
history follows HA retention rules. Backups may still contain saved credentials.

To roll back, create an HA backup, select the previous release in HACS → Redownload
and restart. For a manual rollback replace just the integration directory with the
previous archive. Recheck the entry and entity availability. Version 0.1.0 has no
earlier published release to roll back to: uninstall is the initial fallback.

## Development

```sh
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python -r requirements-test.txt
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python -m compileall -q custom_components
.venv/bin/pytest --cov=custom_components.nextink_s3
```

Network sockets are disabled in automated tests. Fixtures are synthetic; none are
authenticated page captures. MIT license. Maintainer: [pierrec18](https://github.com/pierrec18).
