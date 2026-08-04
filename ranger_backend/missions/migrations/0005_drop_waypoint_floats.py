# ─── RANGER V3 START: F10.1 drop waypoint floats ───
"""
CP4 — irreversible, same terms as core.0007.

Drops Waypoint.latitude/longitude. `location` is the source of truth; the
property shim keeps `wp.latitude` working for any caller that wants a scalar.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("missions", "0004_waypoint_location_required"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="waypoint",
            name="latitude",
        ),
        migrations.RemoveField(
            model_name="waypoint",
            name="longitude",
        ),
    ]
# ─── RANGER V3 END: F10.1 drop waypoint floats ───
