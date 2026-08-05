# ─── RANGER V3 START: satellite integration model tests ───
"""CP1 model tests: geometry, tenancy, and the tile-expiry contract.

Deliberately no GEE here — CP1 has no client. These cover the schema only:
that geometry round-trips, that the tenancy asymmetry works as designed, and
that the tile-staleness rule (the thing most likely to fail silently in a
demo) behaves.
"""
from datetime import date, timedelta

import pytest
from django.utils import timezone

from core.geo import polygon_from_bbox
from satellite_integration.models import (
    SatelliteDataset,
    SatelliteImage,
    SatelliteQuery,
)

# Forole, from the KNRA survey (report Fig. 3.7 axes).
FOROLE_BBOX = (37.9668, 3.7160, 37.9678, 3.7175)


@pytest.fixture
def dataset(db):
    return SatelliteDataset.objects.create(
        name="Sentinel-2 SR Harmonized",
        code="s2",
        provider=SatelliteDataset.Provider.ESA,
        gee_collection_id="COPERNICUS/S2_SR_HARMONIZED",
        resolution_m=10,
        temporal_resolution_days=5,
        scale=SatelliteDataset.Scale.SITE,
        archive_start=date(2017, 3, 28),
    )


@pytest.fixture
def query(db, org, dataset):
    return SatelliteQuery.objects.create(
        organization=org,
        dataset=dataset,
        geometry=polygon_from_bbox(*FOROLE_BBOX),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 8, 1),
        max_cloud_pct=20.0,
        label="forole-s2-2026",
    )


@pytest.mark.django_db
class TestSatelliteDataset:

    def test_code_is_unique(self, dataset):
        from django.db.utils import IntegrityError

        with pytest.raises(IntegrityError):
            SatelliteDataset.objects.create(
                name="Duplicate", code="s2",
                provider=SatelliteDataset.Provider.ESA,
                gee_collection_id="OTHER/COLLECTION",
                resolution_m=10, temporal_resolution_days=5,
            )

    def test_unverified_by_default(self, dataset):
        """is_verified flips only when a real scene has been retrieved."""
        assert dataset.is_verified is False

    def test_has_no_organization(self, dataset):
        """The catalog is global reference data — deliberately untenanted."""
        assert not hasattr(dataset, "organization")


@pytest.mark.geo
@pytest.mark.django_db
class TestSatelliteQuery:

    def test_aoi_geometry_round_trips(self, query):
        fetched = SatelliteQuery.objects.get(pk=query.pk)
        assert fetched.geometry.srid == 4326
        min_lon, min_lat, max_lon, max_lat = fetched.geometry.extent
        assert (min_lon, min_lat, max_lon, max_lat) == pytest.approx(FOROLE_BBOX, abs=1e-9)

    def test_aoi_contains_the_site(self, query):
        from core.geo import point_from_latlon

        inside = point_from_latlon(lat=3.7167, lon=37.9672)
        assert query.geometry.contains(inside)

    def test_org_scoping_is_direct(self, query, org):
        """Mission pattern, not SensorLog-through-Robot."""
        assert query.organization == org
        assert org.satellite_queries.count() == 1

    def test_starts_pending(self, query):
        assert query.status == SatelliteQuery.Status.PENDING
        assert query.scene_count == 0


@pytest.mark.geo
@pytest.mark.django_db
class TestSatelliteImage:

    def _make(self, query, **kwargs):
        defaults = dict(
            query=query,
            gee_asset_id="COPERNICUS/S2_SR_HARMONIZED/20260115T073241",
            acquisition_date=timezone.now(),
            cloud_cover_pct=4.2,
            geometry=polygon_from_bbox(*FOROLE_BBOX),
        )
        defaults.update(kwargs)
        return SatelliteImage.objects.create(**defaults)

    def test_dataset_is_denormalized_from_query(self, query, dataset):
        """save() fills dataset so scene lookups don't need a join."""
        image = self._make(query)
        assert image.dataset_id == dataset.id

    def test_tenancy_inherited_through_query(self, query, org):
        assert self._make(query).organization == org

    def test_asset_id_unique_per_query(self, query):
        from django.db.utils import IntegrityError

        self._make(query)
        with pytest.raises(IntegrityError):
            self._make(query)

    def test_footprint_intersects_the_aoi(self, query):
        image = self._make(query)
        assert SatelliteImage.objects.filter(
            geometry__intersects=query.geometry
        ).filter(pk=image.pk).exists()

    def test_tiles_stale_when_absent(self, query):
        """No cached URL at all counts as stale — regenerate."""
        assert self._make(query).tiles_are_stale() is True

    def test_tiles_stale_after_expiry(self, query):
        image = self._make(
            query,
            tile_url="https://earthengine.googleapis.com/v1/.../tiles/{z}/{x}/{y}",
            tiles_expire_at=timezone.now() - timedelta(hours=1),
        )
        assert image.tiles_are_stale() is True

    def test_tiles_fresh_before_expiry(self, query):
        image = self._make(
            query,
            tile_url="https://earthengine.googleapis.com/v1/.../tiles/{z}/{x}/{y}",
            tiles_expire_at=timezone.now() + timedelta(days=1),
        )
        assert image.tiles_are_stale() is False

    def test_has_cog_reflects_path(self, query):
        assert self._make(query).has_cog is False
        assert self._make(
            query,
            gee_asset_id="OTHER/ASSET/1",
            cog_path="satellite/forole/s2_20260115.tif",
        ).has_cog is True
# ─── RANGER V3 END: satellite integration model tests ───
