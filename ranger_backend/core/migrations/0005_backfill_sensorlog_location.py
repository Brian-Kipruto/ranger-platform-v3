# ─── RANGER V3 START: F10.1 sensorlog backfill ───
"""
Step 2 of 3 (migrate): populate `location` from the legacy float columns.

Reversible: the reverse writes latitude/longitude back out of the geometry,
so `migrate core 0004` restores the pre-backfill state cleanly.

Point construction is INLINED rather than imported from core.geo. Migrations
are frozen history — importing application code means a future refactor of
geo.py silently changes what this migration did. The lon/lat discipline geo.py
enforces is reproduced here, plus a post-write assertion.
"""
from django.contrib.gis.geos import Point
from django.db import migrations

BATCH = 2000

# Inversion tripwire: (min_lon, min_lat, max_lon, max_lat). Mirrors
# core.geo.KENYA_BBOX at the time of writing.
KENYA_BBOX = (33.9, -4.7, 41.9, 5.5)


def forward(apps, schema_editor):
    SensorLog = apps.get_model("core", "SensorLog")

    total = SensorLog.objects.count()
    done = 0
    batch = []

    for log in SensorLog.objects.only("id", "latitude", "longitude").iterator(chunk_size=BATCH):
        # THE FLIP: Point takes (x, y) == (longitude, latitude).
        log.location = Point(log.longitude, log.latitude, srid=4326)
        batch.append(log)
        if len(batch) >= BATCH:
            SensorLog.objects.bulk_update(batch, ["location"], batch_size=BATCH)
            done += len(batch)
            batch = []
    if batch:
        SensorLog.objects.bulk_update(batch, ["location"], batch_size=BATCH)
        done += len(batch)

    # ── assertions: fail LOUDLY inside the transaction rather than shipping
    #    silently inverted coordinates ──
    missing = SensorLog.objects.filter(location__isnull=True).count()
    if missing:
        raise RuntimeError(f"Backfill incomplete: {missing} of {total} rows still NULL")

    min_lon, min_lat, max_lon, max_lat = KENYA_BBOX
    for log in SensorLog.objects.exclude(location=None).only(
        "id", "latitude", "longitude", "location"
    )[:5]:
        if round(log.location.y, 9) != round(log.latitude, 9):
            raise RuntimeError(
                f"Log {log.id}: location.y={log.location.y} != latitude={log.latitude} "
                f"— coordinates are INVERTED"
            )
        if round(log.location.x, 9) != round(log.longitude, 9):
            raise RuntimeError(
                f"Log {log.id}: location.x={log.location.x} != longitude={log.longitude} "
                f"— coordinates are INVERTED"
            )
        if not (min_lat <= log.location.y <= max_lat and min_lon <= log.location.x <= max_lon):
            raise RuntimeError(
                f"Log {log.id} at ({log.location.y}, {log.location.x}) falls outside "
                f"Kenya {KENYA_BBOX} — likely inverted"
            )

    print(f"\n    backfilled {done}/{total} SensorLog.location, assertions passed")


def reverse(apps, schema_editor):
    """Restore floats from geometry, then null the geometry out."""
    SensorLog = apps.get_model("core", "SensorLog")
    batch = []
    for log in SensorLog.objects.exclude(location=None).only("id", "location").iterator(
        chunk_size=BATCH
    ):
        log.latitude = log.location.y
        log.longitude = log.location.x
        log.location = None
        batch.append(log)
        if len(batch) >= BATCH:
            SensorLog.objects.bulk_update(
                batch, ["latitude", "longitude", "location"], batch_size=BATCH
            )
            batch = []
    if batch:
        SensorLog.objects.bulk_update(
            batch, ["latitude", "longitude", "location"], batch_size=BATCH
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_sensorlog_location"),
    ]

    operations = [
        migrations.RunPython(forward, reverse),
    ]
# ─── RANGER V3 END: F10.1 sensorlog backfill ───
