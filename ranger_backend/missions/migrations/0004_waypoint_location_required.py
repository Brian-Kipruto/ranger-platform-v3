# ─── RANGER V3 START: F10.1 waypoint geometry required ───
"""
Step 3 of 3 (contract) for Waypoint.

Mission.area_of_interest is deliberately NOT touched here — it stays nullable
permanently. A mission without a defined survey boundary is a normal state,
not missing data.
"""
import django.contrib.gis.db.models.fields
from django.db import migrations


def guard(apps, schema_editor):
    Waypoint = apps.get_model("missions", "Waypoint")
    missing = Waypoint.objects.filter(location__isnull=True).count()
    if missing:
        raise RuntimeError(
            f"{missing} Waypoint rows have NULL location. Run 0003 first."
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("missions", "0003_backfill_waypoint_location"),
    ]

    operations = [
        migrations.RunPython(guard, noop),
        migrations.AlterField(
            model_name="waypoint",
            name="location",
            field=django.contrib.gis.db.models.fields.PointField(
                srid=4326,
                help_text="WGS84 target position. Source of truth for coordinates.",
            ),
        ),
    ]
# ─── RANGER V3 END: F10.1 waypoint geometry required ───
