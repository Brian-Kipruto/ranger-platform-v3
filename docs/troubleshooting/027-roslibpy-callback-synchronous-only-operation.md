# 027 — `ros_ingest` connects, receives every fix, writes nothing: `SynchronousOnlyOperation` in the roslibpy callback

*Date: 2026-09-28*

---

## What we saw

First run of `ros_ingest` against the simulated `/fix`:

```
INFO roslibpy: Connection to ROS ready.
Connected. /fix -> SensorLog for RANGER-PRIME-001 (source=simulated). Ctrl-C to stop.
ingest error: SynchronousOnlyOperation('You cannot call this from an async context - use a thread or sync_to_async.')
ingest error: SynchronousOnlyOperation('You cannot call this from an async context - use a thread or sync_to_async.')
...
Stopped. {'error': 9}
```

One error per fix, one fix per second. Connection, subscription and message
delivery all worked.

## The cause

roslibpy delivers subscriber callbacks on its Twisted reactor thread, which
has an event loop running. Django checks for a running event loop before any
ORM call and raises `SynchronousOnlyOperation` if it finds one — it cannot know
the call wouldn't block that loop.

The original `on_fix` called `_ingest` directly, so every `SensorLog.objects.create`
ran on the reactor thread.

It was visible only because `on_fix` wrapped everything in a catch-all that
counts and prints. Without it, the exception would have been raised inside
Twisted, the command would have kept printing nothing and looked idle, and the
database would simply have stayed empty.

## The fix

The callback enqueues; the command's main thread does every ORM call
(ADR-0015, Decision 4):

```python
def on_fix(self, m):
    try:
        self.inbox.put_nowait(m)          # reactor thread: no ORM
    except queue.Full:
        self._count("dropped")

# in handle():
while True:
    try:
        m = self.inbox.get(timeout=1)     # main thread: plain sync
    except queue.Empty:
        m = None
    if m is not None:
        self._ingest(m)                   # ORM happens here
```

Second run: 24 rows in Postgres, verified by query.

## Prevention

- Never touch the ORM from a roslibpy (or any Twisted/asyncio) callback. Hand
  off to a thread that has no event loop.
- Do **not** set `DJANGO_ALLOW_ASYNC_UNSAFE`. It silences the check; it does not
  make the call safe.
- Wrap every network callback in a catch-all that counts and reports. A
  callback that raises doesn't crash the process — it just stops the work
  while everything looks alive.
