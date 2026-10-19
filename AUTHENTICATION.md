# Authentication design and limitations

Native Next.ink credentials only. No LPL/OpenID implementation, browser automation,
JavaScript execution, user-provided cookies, TOTP seeds or S3 access keys.

## HTTP flow

1. GET `https://next.ink/profile/?tab=storage` with an isolated in-memory cookie jar.
2. Return only if all four scoped quota statistics parse successfully.
3. Only an explicit native login form or native login URL permits a login attempt.
4. Parse exactly one `form#loginForm`, require POST, fresh hidden fields including
   `_wpnonce`, supported input controls and submit button. Missing action means the
   current form URL. Unexpected base URL or submit override is refused.
5. Validate destination **before** inserting/sending credentials.
6. POST once; then explicitly GET the storage page and parse the complete quota.

All requests use certificate-verified HTTPS, host `next.ink`, default port/443,
no URL userinfo. Every redirect is checked before following, including 307/308
which can preserve a POST body. Maximum five redirects; 30-second per-request
chain deadline; 2 MiB decompressed body limit. The HTML is parsed, never executed.

One password submission maximum per update. An expired session can trigger a fresh
login; missing quota alone cannot. Explicit credential rejection or interactive
challenge blocks further automatic attempts for this client and requests HA reauth.
Ambiguous login responses remain compatibility errors, not password errors.

HTTP 403 is not classified as invalid credentials. 429 sets a monotonic retry
deadline and feeds HA's coordinator `retry_after`. HTTP-date and delta-seconds
Retry-After are supported. No password retry is sent during the deadline.

## Session lifecycle

HA's `async_create_clientsession` provides the managed TLS connector with a **new
CookieJar per client**, not the shared global cookie jar. On setup/config validation
failure, cancellation and unload, the integration clears cookies, detaches its
session from the managed connector and drops credential references. HA also
registers session cleanup at shutdown. No integration cookie files exist.
Config forms hold no persistent session while awaiting user input, so abandoning
a form does not retain a session. Credentials are only submitted once input is given.

## Storage and logging

Username and password are normal HA config-entry data, **not separately encrypted**.
Configuration access and backups may expose them. Cookies are memory-only; no
diagnostics export is implemented. Log messages use fixed error codes, never HTTP
bodies, full request URLs, request forms, cookies or underlying network exceptions.

Opaque local config entry IDs provide stable entity identifiers. Reauthentication
changes only the password and reloads the same entry. Changing account identity
requires removing/re-adding an entry. Usernames/emails cannot be cross-correlated
without a safe, verified server account identity; alias duplicates remain possible.

## What remains a live validation question

See VALIDATION.md. Public markup does not prove successful native authentication,
cookie lifetime, absence of account-specific CAPTCHA/2FA, authenticated quota markup
or compatibility with an exclusively LPL account. Never treat a 200, redirect or
cookie as proof of login. No invented credentials are sent to production tests.
