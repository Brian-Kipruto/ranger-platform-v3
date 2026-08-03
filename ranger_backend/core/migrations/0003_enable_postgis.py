# ─── RANGER V3 START: postgis extension ───
"""
Enables the PostGIS extension on the database.

Lives in `core` because core.SensorLog is the first model to carry a geometry
column. The missions geometry migration declares a dependency on this one, so
extension creation is deterministically ordered ahead of every AddField that
needs it — rather than relying on Django's migration graph happening to
resolve in a favourable order.

Requires the connecting role to be superuser. The Postgres image grants that
to POSTGRES_USER, so `ranger` qualifies.
"""
from django.contrib.postgres.operations import CreateExtension
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_initial"),
    ]

    operations = [
        CreateExtension("postgis"),
    ]
# ─── RANGER V3 END: postgis extension ───