# ─── RANGER V3 START: seed_datasets tests ───
"""The dataset catalog seeder (F10.2 CP2)."""
from datetime import date

import pytest
from django.core.management import call_command

from satellite_integration.models import SatelliteDataset


@pytest.fixture
def seeded(db):
    call_command("seed_datasets", verbosity=0)
    return SatelliteDataset.objects.all()


@pytest.mark.django_db
class TestSeedDatasets:

    def test_seeds_the_catalog(self, seeded):
        assert seeded.count() == 10

    def test_is_idempotent(self, seeded):
        call_command("seed_datasets", verbosity=0)
        assert SatelliteDataset.objects.count() == 10

    def test_reseeding_preserves_is_verified(self, seeded):
        """is_verified records that a real scene was retrieved. Re-seeding the
        catalog must not quietly reset the DATA PROVIDERS panel to red."""
        s2 = SatelliteDataset.objects.get(code="s2")
        s2.is_verified = True
        s2.save(update_fields=["is_verified"])

        call_command("seed_datasets", verbosity=0)
        assert SatelliteDataset.objects.get(code="s2").is_verified is True

    def test_dry_run_writes_nothing(self, db):
        call_command("seed_datasets", "--dry-run", verbosity=0)
        assert SatelliteDataset.objects.count() == 0

    def test_nothing_starts_verified(self, seeded):
        assert not seeded.filter(is_verified=True).exists()


@pytest.mark.django_db
class TestCatalogCorrectness:
    """These encode judgements that are expensive to rediscover."""

    def test_landsat5_archive_predates_the_drilling(self, seeded):
        """The Amoco Laga Balal well was drilled 22 Dec 1985. If this ever
        fails, the change-detection story has lost its foundation."""
        l5 = SatelliteDataset.objects.get(code="l5")
        assert l5.archive_start < date(1985, 12, 22)
        assert l5.archive_end is not None, "Landsat 5 retired in 2012"

    def test_landsat_5_and_8_share_a_grid(self, seeded):
        """Same resolution is what makes 1985-vs-today comparable without
        resampling."""
        assert (SatelliteDataset.objects.get(code="l5").resolution_m
                == SatelliteDataset.objects.get(code="l8").resolution_m)

    def test_coarse_datasets_are_marked_regional(self, seeded):
        """Survey sites are 100-300 m across. Anything coarser resolves a site
        as one pixel and must never be presented as a per-site measurement."""
        for ds in SatelliteDataset.objects.all():
            if ds.resolution_m > 300:
                assert ds.scale == SatelliteDataset.Scale.REGIONAL, (
                    f"{ds.code} at {ds.resolution_m} m cannot be per-site"
                )

    def test_smap_is_regional(self, seeded):
        """Named explicitly: soil moisture is the key covariate, and claiming
        per-site SMAP is the most tempting available overclaim."""
        assert SatelliteDataset.objects.get(code="smap").scale == (
            SatelliteDataset.Scale.REGIONAL
        )

    def test_site_scale_datasets_can_resolve_a_site(self, seeded):
        for ds in SatelliteDataset.objects.filter(scale=SatelliteDataset.Scale.SITE):
            assert ds.resolution_m <= 30

    def test_collection_ids_are_unique(self, seeded):
        ids = list(seeded.values_list("gee_collection_id", flat=True))
        assert len(ids) == len(set(ids))
# ─── RANGER V3 END: seed_datasets tests ───
