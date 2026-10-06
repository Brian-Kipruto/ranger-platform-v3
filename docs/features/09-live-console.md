# F09 — Live on the Console

*Date: 2026-10-06*
*Branch: `feat/live-console` (from `feat/ros-bridge-gps` @ `50bdc18`)*
*Status: **complete.** A fix taken on the Orin moves its blip on the Dashboard in ~0.7 s, labelled by provenance, for its own org only.*

---

## What this feature does

F08 put a robot's GPS fix into Postgres. F09 puts it on the screen as it
happens: `ros_ingest` saves a `SensorLog`, broadcasts it to an org-scoped
Channels group, and the Dashboard's `<FieldMap>` moves that robot's blip.

This is the platform's first WebSocket and the first time the Dashboard shows
anything that isn't fetched once or DEMO. It runs on `nmea_sim`; `--source live`
on the NEO-6M turns the same blip green with no code change.

| Checkpoint | Proven with | Status |
|---|---|---|
| 2a — consumer + tenancy | 8 pytest cases on the real ASGI stack; manual browser socket received row 24676 | ✅ `66aaa36` |
| 2b — ingest broadcasts | 4 pytest cases; 26/26 rows broadcast; two Redis outages with no row lost | ✅ `8b4a2ca` |
| 2c — the blip moves | Visual sign-off: SIM blip, lag ~700 ms, STALE, reconnect, tenancy | ✅ `1d3142e` |

Decisions: [ADR-0016](../decisions/0016-live-console-websocket-auth.md) (socket
auth, groups, close codes) and
[ADR-0017](../decisions/0017-live-broadcast-explicit-helper.md) (broadcast path,
provenance on the blip). New known gaps: ADR-0005 items 17–18.

---

## Sign-off evidence

### 2a — consumer and tenancy (2026-10-05)

`PYTHONPATH= pytest ros_bridge -v` → 8 passed. The tenancy test connects one
user from each of two orgs, broadcasts a real saved row for org A through the
real helper, and asserts org B receives nothing. Mutation check: with every org
forced into one group, it fails with `org B received org A's data`.

Manual, against Daphne and the Redis layer: a browser console socket opened
with `proto = ranger.v1`; `broadcast_sensorlog()` from `manage.py shell` on row
24676 (`live`, from F08's sign-off) arrived with the same id. Bad credentials
closed `4401` after the handshake.

### 2b — ingest broadcasts (2026-10-06)

- **Flow:** rows 24677–24702, `Stopped. {'saved': 26, 'broadcast': 26}`.
- **DB:** the last three ids in Postgres matched the last three socket messages.
- **Redis down:** two outages in one run →
  `Stopped. {'saved': 244, 'broadcast': 202, 'broadcast_error': 42}`; `DOWN` and
  `recovered` each printed once per outage; ids 24745–24988 contiguous.
- Mutation checks: removing the broadcast call fails 3 tests; removing the
  `try/except` fails 3 tests.

### 2c — the blip moves (2026-10-06, visual sign-off: Brian)

| Check | Result |
|---|---|
| Blip at the sim position (−1.2864, 36.8172), moves without refresh | ✅ |
| Grey, no ping; fleet row `SIM`; header `FIELD MAP · SIM` | ✅ |
| Readout shows live coordinates | ✅ |
| Frames ~1/s; `lag=` 693–710 ms (#25271–25301) | ✅ < 1 s |
| Ingest stopped → red, `STALE`, `· DEMO` within 5 s; restart → back to `SIM` | ✅ |
| Redis stop/start → 4 failed attempts at 1/2/4/8 s backoff, then a new `101`; lines resume | ✅ |
| `client@magadi.com` with ingest running → no blip, header `· DEMO`, socket `101` | ✅ |

The tenancy check reads the header, not just the map: the tag is computed from
every position in the live store regardless of fleet, so a single ByteAnza row
reaching that socket would have shown `· SIM`.

Of the ~700 ms lag, ~220 ms is the residual Orin−PC offset (TS-029); ~480 ms is
pipeline, not yet broken down.

---

## Topology

```
Orin                              PC
gps_node ─/fix─ rosbridge :9090 ──► ros_ingest (sync, main thread)
                                      SensorLog.objects.create()
                                      broadcast_sensorlog(log) ──► Redis channel layer
                                                                     │ group dashboard.org.<id>
Browser ◄── /ws/dashboard/ (Vite /ws proxy) ◄── DashboardConsumer ◄──┘
  LiveFeed → useLiveStore → DashboardPage → <FieldMap blips readout headerSub>
```

## Files

| File | Role |
|---|---|
| `ranger_backend/ros_bridge/broadcast.py` | `dashboard_group()`, `sensorlog_payload()` (from the saved row), `broadcast_sensorlog()` (raises) |
| `ranger_backend/ros_bridge/consumers.py` | `DashboardConsumer`: subprotocol auth, join-before-accept, 4401/4403 after accept, read-only |
| `ranger_backend/ros_bridge/routing.py` | `^ws/dashboard/$` |
| `ranger_backend/ranger_backend/asgi.py` | imports `ros_bridge.routing.websocket_urlpatterns` |
| `ranger_backend/ros_bridge/management/commands/ros_ingest.py` | `_broadcast()` after each save; `broadcast` / `broadcast_error` counters |
| `ranger_backend/ros_bridge/test_consumers.py` | 8 tests: tenancy, disconnect, 4401 ×4 (none, garbage, expired, inactive), 4403, query-string token refused |
| `ranger_backend/ros_bridge/test_ros_ingest.py` | 4 tests: saved → broadcast, skips not broadcast, failure keeps rows, recovery |
| `ranger_backend/pytest.ini` | `ros_bridge` in `testpaths`; `asyncio_default_fixture_loop_scope` |
| `ranger_frontend/src/stores/liveStore.ts` | One validated position per robot; older ids dropped; `reset()` |
| `ranger_frontend/src/components/dashboard/LiveFeed.tsx` | Native `WebSocket`; token as effect dependency; close-code handling; dev `[live] … lag=` log |
| `ranger_frontend/src/pages/DashboardPage.tsx` | Overlays live position/status on the fleet; 5 s staleness; header tag; store reset on user change |
| `ranger_frontend/src/components/map/FieldMap.tsx` | `sim` status; markers moved, not rebuilt, when status/selection unchanged |
| `ranger_frontend/src/components/dashboard/FleetMini.tsx`, `console/StatusDot.tsx` | `sim` entries |

## Payload

Row 24702, values rounded:

```json
{"type": "sensorlog", "id": 24702, "robot": "RANGER-PRIME-001",
 "ts": "2026-10-06T07:34:20Z", "lat": -1.286423, "lon": 36.817228, "source": "simulated"}
```

## Running it

Start the Orin stack and `ros_ingest` as in [F08](./08-ros-bridge-gps.md#running-it)
— clock first, with the corrected fallback (TS-029). Then on the PC:

```bash
docker compose up -d && docker exec ranger_redis redis-cli ping   # PONG
cd ranger_backend && python manage.py runserver                   # banner: Daphne
cd ranger_frontend && npm run dev                                 # http://localhost:5173
```

Debug socket without the frontend — DevTools console on `http://localhost:8000/admin/`:

```js
const {access} = await (await fetch('/api/auth/token/',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:'…',password:'…'})})).json();
const ws = new WebSocket('ws://localhost:8000/ws/dashboard/', ['ranger.v1', 'jwt.'+access]);
ws.onmessage = e => console.log(JSON.parse(e.data));
ws.onclose = e => console.log('closed', e.code);
```

## Gotchas

**Channels group names reject colons.** `dashboard:<org>` is invalid; use
`dashboard.org.<id>`.

**`ros_bridge` must be in `pytest.ini` `testpaths`.** Otherwise its tests are
never collected, which looks like passing.

**Two `dashboard/` sockets in dev** — StrictMode mounts `LiveFeed` twice; the
first closes immediately. One in production.

**Browser `WebSocket connection … failed` errors during a Redis outage** are the
reconnect attempts; the consumer's `group_add` fails until Redis is back.

**`broadcast: N` proves `group_send` didn't raise, not delivery** — a send to an
empty group succeeds. Delivery is proven in the browser.

**A passing build is not a working dev server** (TS-030).

## Open items

- **DEMO still claims LIVE.** `FLEET_STATUS_DEMO["RANGER-PRIME-001"]` is
  `status: "live"`, and the top-bar `3 LIVE · 1 MQTT · 1 OFF` is hard-coded.
  Both show when no live data is flowing.
- **No snapshot on connect.** A fresh page shows DEMO coordinates until the first
  push; rows saved during a Redis outage are never pushed (ADR-0017).
- **Socket auth is connect-time only; nginx/wss not configured** (ADR-0005 #17, #18).
- **~480 ms of pipeline lag unexplained.** Under budget; stamp at each hop to find it.
- **Field time** (TS-025, TS-029) and **`--region` for Rabat** (F08) still open —
  both block the finale.
- Live readout heading/speed are DEMO; only coordinates are live.
- Per-robot, alerts and mission consumers — not built.
- `run_simulation` live mode doesn't call `broadcast_sensorlog`.
