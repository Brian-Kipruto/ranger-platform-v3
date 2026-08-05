# ─── RANGER V3 START: check_gee ───
"""Connectivity and catalog check for Earth Engine (F10.2 CP4).

Answers two questions that are otherwise conflated:

  * Do our credentials work at all?
  * Is every collection ID in the catalog real?

The second matters because the IDs were typed from Google's documentation. A
typo does not raise — `ee.ImageCollection("TYPO/ID")` fails only when
evaluated, and inside a filtered search it can surface as an empty result,
which reads as "no scenes over this AOI". This command makes that failure
loud and cheap to find.

Does NOT set is_verified: that flag means a real scene was retrieved and
stored (CP5), which is a stronger claim than "the ID resolves".
"""
from django.core.management.base import BaseCommand

from satellite_integration import gee_client
from satellite_integration.models import SatelliteDataset


class Command(BaseCommand):
    help = "Verify Earth Engine credentials and every catalog collection ID."

    def add_arguments(self, parser):
        parser.add_argument(
            "--code", type=str, default=None,
            help="Check a single dataset by code, e.g. 's2'.",
        )

    def handle(self, *args, **options):
        if not gee_client.is_configured():
            self.stderr.write(self.style.ERROR(
                "Earth Engine is not configured. Set GEE_PROJECT_ID, "
                "GEE_SERVICE_ACCOUNT_EMAIL and GEE_KEY_PATH in .env."
            ))
            return

        try:
            gee_client.initialize()
        except gee_client.GEEError as exc:
            self.stderr.write(self.style.ERROR(f"connection FAILED: {exc}"))
            return
        self.stdout.write(self.style.SUCCESS("credentials OK"))

        qs = SatelliteDataset.objects.filter(is_active=True)
        if options["code"]:
            qs = qs.filter(code=options["code"])

        ok = bad = 0
        for dataset in qs.order_by("code"):
            try:
                exists = gee_client.collection_exists(dataset.gee_collection_id)
            except gee_client.GEEError as exc:
                self.stdout.write(
                    f"  {dataset.code:<11} ERROR   {dataset.gee_collection_id} — {exc}"
                )
                bad += 1
                continue

            if exists:
                self.stdout.write(self.style.SUCCESS(
                    f"  {dataset.code:<11} ok      {dataset.gee_collection_id}"
                ))
                ok += 1
            else:
                self.stdout.write(self.style.ERROR(
                    f"  {dataset.code:<11} MISSING {dataset.gee_collection_id}"
                ))
                bad += 1

        style = self.style.SUCCESS if not bad else self.style.WARNING
        self.stdout.write(style(f"\n{ok} collection(s) resolved, {bad} problem(s)"))
        if bad:
            self.stdout.write(
                "Fix the IDs in seed_datasets.py and re-run `seed_datasets`."
            )
# ─── RANGER V3 END: check_gee ───
