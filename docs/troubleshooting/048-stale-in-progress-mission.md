# 048 — A leftover IN_PROGRESS mission would absorb every fix and block START

*Date: 2026-10-29 · caught by the pre-migration check*

---

## What we saw

Before applying `missions/0007` (one running mission per robot), the pre-check:

```bash
docker exec -i ranger_postgres psql -U ranger -d ranger_v3 -P pager=off -c "SELECT robot_id, count(*), array_agg(id) FROM missions_mission WHERE status='IN_PROGRESS' GROUP BY robot_id;"
```

returned `1 | 1 | {1}`: mission #1 "Sim Test Mission", IN_PROGRESS on
RANGER-PRIME-001 — created long ago by the old `run_simulation`, never finished.

## The cause

The migration would apply (one per robot). But with F15's ingest hook, every fix from
robot 1 would be offered to #1 and attached to it, and START on any new mission for
robot 1 would return 409 ("already has a mission in progress").

## The fix

```bash
docker exec -i ranger_postgres psql -U ranger -d ranger_v3 -P pager=off -c "UPDATE missions_mission SET status='ABORTED', updated_at=now() WHERE id=1 AND status='IN_PROGRESS' RETURNING id, name, status;"
```

ABORTED, not COMPLETED: it never ran to completion. Its rows are untouched.

## Prevention

- Run the pre-check before a bench run as well as before migrating.
- START answering 409 with "already has a mission in progress" means exactly this:
  find the robot's running mission before anything else.
