# ADR-0016: Live console WebSocket — auth in the subprotocol, org-scoped groups, join before accept

- **Status:** Accepted
- **Date:** 2026-10-06
- **Feature:** F09 (Live on the Console)
- **Supersedes:** none
- **Related:** ADR-0002 (tenancy via organization FK), ADR-0003 (token storage), ADR-0005 (known gaps — items 17–18 added by this ADR), ADR-0006 (SensorLog tenancy through Robot), ADR-0017 (broadcast path)

## Context

F09 adds the platform's first WebSocket: `/ws/dashboard/`, a read-only feed of
saved `SensorLog` rows to the Dashboard. Channels, Daphne and the Redis layer
were installed in Phase 1 with an empty `websocket_urlpatterns`.

Three things had to be decided before any code: how a browser authenticates a
socket (it cannot set an `Authorization` header), how one org's rows are kept
from another org's sockets, and what a rejected client sees.

## Decision 1 — The access token rides in `Sec-WebSocket-Protocol`

```js
new WebSocket(url, ["ranger.v1", "jwt.<access token>"])
```

The consumer reads the `jwt.`-prefixed entry, validates it with simplejwt's
`AccessToken` (signature, type, expiry), loads the user (`is_active=True`) and
echoes `ranger.v1`. The token is never in the URL.

| Option | Verdict |
|---|---|
| Token in the query string (`?token=…`) | **Rejected** — the original handoff recommendation. URLs land in Daphne, nginx and proxy access logs; a 15-minute bearer token in a log file is a credential in a log file. A test asserts `?token=` is not accepted. |
| Token in `Sec-WebSocket-Protocol` | **Chosen** — not logged, no extra endpoint, ~10 lines. The server must echo a protocol the client offered or the browser fails the handshake. |
| Session/refresh cookie | **Rejected** — the refresh cookie is httpOnly, SameSite=Strict and meant for `/api/auth/*` only (ADR-0003). Ambient-cookie WebSocket auth is also the precondition for cross-site WebSocket hijacking. |
| One-time ticket from a REST endpoint | **Deferred** — strongest (short-lived, single-use) but needs an endpoint and a store. Revisit with production auth hardening. |

JWT characters (`A-Z a-z 0-9 - _ .`) are valid HTTP token characters, so the
token is a legal subprotocol value.

## Decision 2 — Auth at connect only

A socket is authenticated once, at `connect()`. It outlives its 15-minute access
token and is not closed by a blacklist or logout elsewhere. A reconnect must
present a current token.

The frontend makes the token an effect dependency of the socket, so a silent
refresh (axios interceptor) closes the old socket and opens a new one. On
`4401` the client makes one authenticated HTTP call so the interceptor can
refresh; it does not retry blindly with the same token.

**Consequences.** Revocation does not reach an open socket. Logged as ADR-0005
item 17.

## Decision 3 — One group per organization, joined before accept

Group name: `dashboard.org.<org_id>`, produced by `ros_bridge.broadcast.dashboard_group()`,
which both the sender and the consumer call. The vault's `dashboard:<org>` is
invalid — Channels group names must match `^[a-zA-Z0-9\-_.]+$`.

The consumer authenticates, **joins the group, then accepts**. Once the client
sees the handshake complete, it is already subscribed; no broadcast can fall
between `accept` and `group_add`. (The first draft accepted first; the test
harness would have raced on it.)

Tenancy follows ADR-0006: the row's org is `log.robot.organization_id`. The
tenancy test connects a user from each of two orgs, broadcasts a real saved row
for org A, and asserts org B receives nothing. A mutation check — forcing every
org into one group — makes that test fail.

## Decision 4 — Rejections close *after* accept, with distinct codes

| Code | Meaning | Client behaviour |
|---|---|---|
| `4401` | Missing, malformed, expired or unknown-user token; inactive user | One HTTP call to trigger refresh; no blind reconnect |
| `4403` | Valid user with no organization | Stop; retrying cannot fix it |
| other (`1006`, `1011`) | Server or Redis gone | Reconnect, backoff 1 s → 10 s cap |

A close before `accept` reaches the browser as an HTTP 403 handshake failure
and a bare `1006`; the custom code is lost. Accepting first costs nothing — the
socket is closed before anything is sent — and makes the failure diagnosable
from DevTools.

## Consequences

- The feed is read-only: `receive_json` ignores client messages.
- `AllowedHostsOriginValidator` stays in front of the router; tests send an
  `Origin` header and run against the real `application`, not the bare consumer.
- ORM work in the async consumer goes through `database_sync_to_async`; tests
  need `transaction=True` and a connection-closing fixture (TS-028).
