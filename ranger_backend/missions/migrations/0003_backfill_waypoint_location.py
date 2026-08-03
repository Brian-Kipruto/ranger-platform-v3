# ─── RANGER V3 START: F10.1 waypoint backfill ───
"""
Step 2 of 3 (migrate) for Waypoint.

Small table (4 rows at time of writing) — but the RISKIEST backfill in F10.1,
because waypoints are invisible to the API contract diff. No endpoint
serializes them, so an inversion here would not show up in capture/compare;
it would surface as the simulator driving toward a target in the wrong
hemisphere. Hence the assertion covers EVERY row, not a sample of five.
"""
from django.contrib.gis.geos import Point
from django.db import migrations

KENYA_BBOX = (33.9, -4.7, 41.9, 5.5)


def forward(apps, schema_editor):
    Waypoint = apps.get_model("missions", "Waypoint")
    min_lon, min_lat, max_lon, max_lat = KENYA_BBOX

    updated = []
    for wp in Waypoint.objects.only("id", "latitude", "longitude").iterator(chunk_size=500):
        # THE FLIP: Point takes (x, y) == (longitude, latitude).
        wp.location = Point(wp.longitude, wp.latitude, srid=4326)
        updated.append(wp)
    if updated:
        Waypoint.objects.bulk_update(updated, ["location"], batch_size=500)

    # Assert on every row — this table is small and unwatched by the API diff.
    for wp in Waypoint.objects.exclude(location=None).only(
        "id", "latitude", "longitude", "location"
    ):
        if round(wp.location.y, 9) != round(wp.latitude, 9) or \
           round(wp.location.x, 9) != round(wp.longitude, 9):
            raise RuntimeError(
                f"Waypoint {wp.id}: geometry ({wp.location.y}, {wp.location.x}) does not "
                f"match floats ({wp.latitude}, {wp.longitude}) — INVERTED"
            )
        if not (min_lat <= wp.location.y <= max_lat and min_lon <= wp.location.x <= max_lon):
            raise RuntimeError(
                f"Waypoint {wp.id} at ({wp.location.y}, {wp.location.x}) falls outside "
                f"Kenya {KENYA_BBOX} — likely inverted"
            )

    missing = Waypoint.objects.filter(location__isnull=True).count()
    if missing:
        raise RuntimeError(f"Backfill incomplete: {missing} waypoints still NULL")

    print(f"\n    backfilled {len(updated)} Waypoint.location, all rows asserted")


def reverse(apps, schema_editor):
    Waypoint = apps.get_model("missions", "Waypoint")
    updated = []
    for wp in Waypoint.objects.exclude(location=None).only("id", "location").iterator(
        chunk_size=500
    ):
        wp.latitude = wp.location.y
        wp.longitude = wp.location.x
        wp.location = None
        updated.append(wp)
    if updated:
        Waypoint.objects.bulk_update(
            updated, ["latitude", "longitude", "location"], batch_size=500
        )


class Migration(migrations.Migration):

    dependencies = [
        ("missions", "0002_waypoint_location_mission_aoi"),
    ]

    operations = [
        migrations.RunPython(forward, reverse),
    ]
# ─── RANGER V3 END: F10.1 waypoint backfill ───
