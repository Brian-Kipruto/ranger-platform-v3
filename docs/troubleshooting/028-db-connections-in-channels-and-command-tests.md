# 028 — Database connections in Channels and management-command tests: three traps

*Date: 2026-10-06*

---

## What we saw

Writing the F09 tests (`ros_bridge/test_consumers.py`, `test_ros_ingest.py`):

**1. Teardown fails after every async consumer test passes.**

```
PytestWarning: Error when trying to teardown test databases:
OperationalError('database "test_ranger_v3" is being accessed by other users
DETAIL:  There is 1 other session using the database.')
```

**2. Every `_ingest` test after the first write errors.**

```
django.db.utils.OperationalError: the connection is closed
```

**3. Anticipated, not hit** (designed around from the start): users created in a
default `django_db` test are invisible to the consumer, so every connect closes
`4401` and the tenancy test fails for the wrong reason.

## The causes

**Trap 3 → `transaction=True`.** `database_sync_to_async` runs the ORM call on a
worker thread with its **own** connection. The default `django_db` test wraps
everything in one uncommitted transaction on the main connection; the worker
cannot see those rows.

**Trap 1 → the worker's connection is never closed.** With `transaction=True`,
data is committed and visible, but the worker thread keeps its connection open
after the test. At session end Postgres refuses to drop a database with a live
session.

**Trap 2 → `close_old_connections()` inside a test transaction.** `ros_ingest._ingest`
calls it before each write — correct for a long-running process that must
recover from a dropped connection. Inside pytest-django's per-test transaction
(`in_atomic_block`), closing the connection marks it unusable for the rest of
the test.

## The fix

```python
# test_consumers.py
pytestmark = [pytest.mark.asyncio, pytest.mark.django_db(transaction=True)]

@pytest_asyncio.fixture(autouse=True)
async def close_worker_db_connections():
    yield
    await sync_to_async(connections.close_all)()   # runs on the worker thread
```

```python
# test_ros_ingest.py
@pytest.fixture(autouse=True)
def keep_test_connection(monkeypatch):
    monkeypatch.setattr(mod, "close_old_connections", lambda: None)
```

Also: `asyncio_default_fixture_loop_scope = function` in `pytest.ini` (pytest-asyncio
0.25 warns without it), the in-memory channel layer via the `settings` fixture,
and `await communicator.wait()` after a close so no consumer task outlives the
test.

## Prevention

- Async consumer test that touches the ORM → `transaction=True` **and** the
  closing fixture, together.
- Code that manages its own connections (`close_old_connections`) → neutralise
  it in the test, at the name the module imported.
- Run with `-W error::pytest.PytestUnraisableExceptionWarning` once when adding
  async tests; dangling tasks show up as unraisable warnings, not failures.
