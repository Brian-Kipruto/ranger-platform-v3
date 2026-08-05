# ─── RANGER V3 START: seed_datasets ───
"""Seeds the satellite dataset catalog (F10.2 CP2).

Idempotent — `update_or_create` keyed on `code`, matching seed_demo's
discipline. Safe to re-run; will not clobber `is_verified`, which is set by
fetch_scenes when a real scene is actually retrieved.

Two things encoded here that are easy to get wrong later:

1. `scale` is not decoration. The Marsabit survey sites are 100-300 m across.
   Anything coarser than that resolves the site as a SINGLE PIXEL, which makes
   it a regional covariate — useful for explaining variance, useless as a
   per-site measurement. SMAP at 11 km covers all six sites and most of the
   county in one cell. Claiming per-site soil moisture from SMAP would be
   the kind of error a reviewer catches instantly.

2. `archive_start` on Landsat 5 is 1984. The Amoco Laga Balal well was drilled
   22 December 1985 — inside the archive. That single date is why the change
   detection story exists at all, so it lives in the data rather than in a
   slide.

Collection IDs are from the GEE catalog and are NOT verified by this command.
Run `verify_collections.py` (see docs) against real credentials to confirm
each ID resolves before relying on it.
"""
from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction

from satellite_integration.models import SatelliteDataset

P = SatelliteDataset.Provider
S = SatelliteDataset.Scale

DATASETS = [
    {
        "code": "s2",
        "name": "Sentinel-2 Surface Reflectance (Harmonized)",
        "provider": P.ESA,
        "gee_collection_id": "COPERNICUS/S2_SR_HARMONIZED",
        "resolution_m": 10,
        "temporal_resolution_days": 5,
        "scale": S.SITE,
        "bands": ["B2", "B3", "B4", "B8", "B11", "B12", "SCL"],
        "archive_start": date(2017, 3, 28),
        "description": (
            "Optical multispectral. Primary workhorse: NDVI and bare-soil "
            "fraction as covariates for gamma attenuation, plus iron-oxide and "
            "clay band ratios for the Forole Zr / Kargi Sr anomalies, and "
            "salinity indices over the Chalbi (Chumvi) salt surface the field "
            "team could not reach."
        ),
    },
    {
        "code": "s1",
        "name": "Sentinel-1 SAR GRD",
        "provider": P.ESA,
        "gee_collection_id": "COPERNICUS/S1_GRD",
        "resolution_m": 10,
        "temporal_resolution_days": 6,
        "scale": S.SITE,
        "bands": ["VV", "VH", "angle"],
        "archive_start": date(2014, 10, 3),
        "description": (
            "C-band radar. Cloud-independent, and backscatter responds to "
            "surface soil moisture and roughness — the finest-resolution "
            "moisture proxy available for sites this small."
        ),
    },
    {
        "code": "s5p_no2",
        "name": "Sentinel-5P NO2 (OFFL L3)",
        "provider": P.ESA,
        "gee_collection_id": "COPERNICUS/S5P/OFFL/L3_NO2",
        "resolution_m": 7000,
        "temporal_resolution_days": 1,
        "scale": S.REGIONAL,
        "bands": ["tropospheric_NO2_column_number_density"],
        "archive_start": date(2018, 6, 28),
        "description": (
            "Atmospheric trace gas. Regional only — one cell spans the whole "
            "survey area. Relevant to the platform's air-quality story, not to "
            "per-site radiological work."
        ),
    },
    {
        "code": "smap",
        "name": "SMAP L4 Global Soil Moisture",
        "provider": P.NASA,
        "gee_collection_id": "NASA/SMAP/SPL4SMGP/007",
        "resolution_m": 11000,
        "temporal_resolution_days": 0.125,
        "scale": S.REGIONAL,
        "bands": ["sm_surface", "sm_rootzone", "soil_temp_layer1"],
        "archive_start": date(2015, 3, 31),
        "description": (
            "Soil moisture. Scientifically the most important regional "
            "covariate here: soil water attenuates terrestrial gamma, so "
            "moisture explains real variance in measured dose rates. One pixel "
            "covers every survey site — a county-scale control variable, never "
            "a per-site measurement."
        ),
    },
    {
        "code": "modis_lst",
        "name": "MODIS Terra Land Surface Temperature (MOD11A1)",
        "provider": P.NASA,
        "gee_collection_id": "MODIS/061/MOD11A1",
        "resolution_m": 1000,
        "temporal_resolution_days": 1,
        "scale": S.REGIONAL,
        "bands": ["LST_Day_1km", "LST_Night_1km", "QC_Day"],
        "archive_start": date(2000, 2, 24),
        "description": (
            "Daily land surface temperature. Long consistent record for "
            "seasonal context; too coarse to resolve a 200 m site."
        ),
    },
    {
        "code": "l5",
        "name": "Landsat 5 TM Collection 2 Level 2",
        "provider": P.USGS,
        "gee_collection_id": "LANDSAT/LT05/C02/T1_L2",
        "resolution_m": 30,
        "temporal_resolution_days": 16,
        "scale": S.SITE,
        "bands": ["SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B7", "ST_B6"],
        "archive_start": date(1984, 3, 16),
        "archive_end": date(2012, 5, 5),
        "description": (
            "THE ARCHIVE. Opens March 1984; the Amoco Laga Balal well was "
            "drilled 22 December 1985. This collection contains imagery of the "
            "drilling period itself, which is the only independent visual "
            "record of what happened at these sites."
        ),
    },
    {
        "code": "l8",
        "name": "Landsat 8 OLI/TIRS Collection 2 Level 2",
        "provider": P.USGS,
        "gee_collection_id": "LANDSAT/LC08/C02/T1_L2",
        "resolution_m": 30,
        "temporal_resolution_days": 16,
        "scale": S.SITE,
        "bands": ["SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7", "ST_B10"],
        "archive_start": date(2013, 3, 18),
        "description": (
            "Modern end of the Landsat record. Same 30 m grid as Landsat 5, so "
            "1985 and today are directly comparable without resampling — that "
            "continuity is what makes four-decade change detection defensible."
        ),
    },
    {
        "code": "l9",
        "name": "Landsat 9 OLI-2/TIRS-2 Collection 2 Level 2",
        "provider": P.USGS,
        "gee_collection_id": "LANDSAT/LC09/C02/T1_L2",
        "resolution_m": 30,
        "temporal_resolution_days": 16,
        "scale": S.SITE,
        "bands": ["SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7", "ST_B10"],
        "archive_start": date(2021, 10, 31),
        "description": "Paired with Landsat 8 for an effective 8-day revisit.",
    },
    {
        "code": "chirps",
        "name": "CHIRPS Daily Precipitation",
        "provider": P.UCSB,
        "gee_collection_id": "UCSB-CHG/CHIRPS/DAILY",
        "resolution_m": 5566,
        "temporal_resolution_days": 1,
        "scale": S.REGIONAL,
        "bands": ["precipitation"],
        "archive_start": date(1981, 1, 1),
        "description": (
            "Rainfall since 1981. Context for soil moisture, and for the "
            "vegetation flush that blocked road access to Chumvi."
        ),
    },
    {
        "code": "era5_land",
        "name": "ERA5-Land Hourly Reanalysis",
        "provider": P.ECMWF,
        "gee_collection_id": "ECMWF/ERA5_LAND/HOURLY",
        "resolution_m": 11132,
        "temporal_resolution_days": 0.0417,
        "scale": S.REGIONAL,
        "bands": [
            "temperature_2m",
            "volumetric_soil_water_layer_1",
            "total_precipitation_hourly",
        ],
        "archive_start": date(1950, 1, 2),
        "description": (
            "Reanalysis back to 1950 — the only source here that predates the "
            "1980s exploration. Coarse, but it can characterise conditions at "
            "the time of drilling."
        ),
    },
]


class Command(BaseCommand):
    help = "Seed the satellite dataset catalog. Idempotent."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would change without writing.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry = options["dry_run"]
        created_n = updated_n = 0

        for spec in DATASETS:
            code = spec["code"]
            existing = SatelliteDataset.objects.filter(code=code).first()

            if dry:
                verb = "would update" if existing else "would create"
                self.stdout.write(f"  {verb}: {code:<10} {spec['name']}")
                continue

            # is_verified is deliberately NOT in defaults: it records that a
            # real scene was retrieved, and re-seeding must not reset it.
            _, created = SatelliteDataset.objects.update_or_create(
                code=code,
                defaults={k: v for k, v in spec.items() if k != "code"},
            )
            if created:
                created_n += 1
            else:
                updated_n += 1
            self.stdout.write(
                f"  {'created' if created else 'updated'}: {code:<10} {spec['name']}"
            )

        if dry:
            self.stdout.write(self.style.WARNING("dry run — nothing written"))
            return

        total = SatelliteDataset.objects.count()
        site = SatelliteDataset.objects.filter(scale=S.SITE).count()
        self.stdout.write(self.style.SUCCESS(
            f"catalog: {total} datasets ({created_n} created, {updated_n} updated) "
            f"— {site} per-site, {total - site} regional"
        ))
        self.stdout.write(
            "Collection IDs are unverified until fetch_scenes retrieves from them."
        )
# ─── RANGER V3 END: seed_datasets ───
