# 012 — Robot filter had no value to send (serializer string ID vs filter integer ID)

> Feature 05 (05a serializer ↔ 05b filter). Severity: low (caught at build
> time, before it shipped). Also a cross-layer-coupling lesson.

## Symptom

While building the 05b filter dropdowns, the robot filter could not be made to
work: the dropdown could show robot names, but there was no value to send back
to the list endpoint that the backend would accept.

## Diagnosis

The list endpoint filters by **integer** `robot_id`
(`qs.filter(robot_id=int(robot_id))`). But `DataLogSerializer` originally
exposed only `robot_id_str` (e.g. `"RANGER-PRIME-001"`), not the integer PK. So
the frontend had the human ID for display but no integer to filter with. The
mission filter was fine — `mission_id` is the integer PK and the serializer
exposed it; only the robot path had the mismatch.

V2 avoided this because it had a separate `/api/robots/` endpoint returning
`{id, robot_id_str, name}`, so the dropdown got real PKs from there. Feature 05
deliberately does not build that endpoint (out of scope), which left the gap:
serializer exposes the string ID, filter wants the integer ID, nothing bridges
them.

## Fix

Add `robot_id` (integer PK) to `DataLogSerializer`:

```python
robot_id = serializers.IntegerField(source="robot.id", read_only=True)
```

plus `"robot_id"` in the `fields` list. `robot.id` is always present (every log
has a robot via a CASCADE FK), so no null guard is needed.

**Coupling caught in the same step:** the CSV export reuses the serializer and
writes rows via `csv.DictWriter(response, fieldnames=...)`. Adding a serializer
field without adding it to `fieldnames` makes `DictWriter` raise
`ValueError: dict contains fields not in fieldnames` on the first export. So the
fix was two edits, not one — the new field had to be added to the export's
`fieldnames` too.

## Lesson

Two lessons. First: when a serializer is the contract for both display *and*
filtering, make sure it exposes whatever the filter keys on — exposing a
human-readable ID is not the same as exposing the filter key. Second: a
serializer feeding a `DictWriter`-based CSV export is coupled to that writer's
`fieldnames`; any field change is a two-place edit, and the failure (a 500 on
export) is invisible until someone downloads. Building the consumer (the
frontend filter) is what surfaced the first; tracing the shared serializer is
what surfaced the second before it shipped.

## Related

- `features/05-data-explorer.md`
- `decisions/0006-sensorlog-tenancy-through-robot.md` (why robot is the join
  target in the first place)