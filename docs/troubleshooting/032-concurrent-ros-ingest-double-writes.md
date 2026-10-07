# 032 — Two `ros_ingest` processes at once: rows appear during a run that saved nothing

*Date: 2026-10-07*

---

## What we saw

F11's negative proof: run `ros_ingest` with the default region against the
Rabat sim, and show it writes nothing.

```
 26548                                   ← max(id) before
Connected. … (source=simulated, region=kenya).
skip: Coordinate (lat=34.02…, lon=-6.84…) falls outside the expected region …   ×11
Stopped. {'out_of_region': 11}
 26559                                   ← max(id) after
```

The process saved nothing, yet eleven new rows appeared in the eleven seconds it
ran.

## The cause

The previous step's `ros_ingest --region rabat` was still running in another
terminal. Both processes subscribe to `/fix` through the same rosbridge and both
receive every fix; each writes whatever its own guard accepts. Nothing stops two
ingest processes for the same robot from running together.

Confirmed by provenance:

```sql
SELECT id, provenance_note FROM core_sensorlog WHERE id BETWEEN 26549 AND 26559;
-- all 11: … · region=rabat   → the other process
```

Here the regions differed, so the result was contamination of the check. With
the **same** region, every fix would be written twice.

## The fix

Proved the negative by provenance instead of by row count:

```sql
SELECT
  count(*) FILTER (WHERE provenance_note LIKE '%region=kenya'
                   AND NOT ST_Within(location, ST_MakeEnvelope(33.9,-4.7,41.9,5.5,4326)))   AS kenya_outside_kenya,
  count(*) FILTER (WHERE provenance_note LIKE '%region=rabat'
                   AND NOT ST_Within(location, ST_MakeEnvelope(-7.54,33.32,-6.14,34.72,4326))) AS rabat_outside_rabat
FROM core_sensorlog;
-- 0 | 0
```

## Prevention

- Before any check that counts rows: `pgrep -af ros_ingest` must print exactly
  what you expect.
- Stop an ingest with Ctrl-C and read its `Stopped.` line before starting the next.
- Prefer provenance-based proofs (`provenance_note`, `source`) to `max(id)` or
  `count(*)` deltas — they say *which* writer, not just *that* something wrote.
- Not built: a per-robot lock (e.g. a Postgres advisory lock taken in
  `handle()`). Worth it before an unattended or multi-operator deployment.
