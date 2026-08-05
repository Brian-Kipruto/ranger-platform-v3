# ─── RANGER V3 START: dataset cloud property ───
"""Adds `cloud_property` to SatelliteDataset (F10.2 CP4).

Cloud metadata field names differ per collection — Sentinel-2 uses
CLOUDY_PIXEL_PERCENTAGE, Landsat Collection 2 uses CLOUD_COVER, and radar and
reanalysis products have none at all. The client needs to know which, and the
catalog is the right place for that: hardcoding a prefix-to-property map
inside gee_client would duplicate the catalog and drift from it.

Blank means "this product has no cloud concept". That matters: filtering on
an absent property returns an EMPTY collection rather than an error, which is
indistinguishable from "no scenes available" — a silent, plausible-looking
wrong answer.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("satellite_integration", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="satellitedataset",
            name="cloud_property",
            field=models.CharField(
                blank=True,
                default="",
                max_length=50,
                help_text="Scene property holding cloud cover percent, e.g. "
                          "CLOUDY_PIXEL_PERCENTAGE (Sentinel-2) or CLOUD_COVER "
                          "(Landsat C2). Blank = product has no cloud metadata; "
                          "cloud filters must then be skipped, not applied.",
            ),
        ),
    ]
# ─── RANGER V3 END: dataset cloud property ───
