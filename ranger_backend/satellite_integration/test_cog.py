# ─── RANGER V3 START: cog pipeline tests ───
"""COG conversion, validation, and storage layout (F10.2 CP5).

No Earth Engine, no database, no network. The whole raster pipeline is
exercised against a synthetic GeoTIFF built by the `geotiff_bytes` fixture,
which means these tests catch a rasterio or rio-cogeo regression on a laptop
with no credentials at all.

The assertions worth reading twice are the ones about atomicity and about
footprints. A `.partial` file surviving a failure would leave a path that a
SatelliteImage row could point at; a footprint taken from anywhere but the
file itself would over-claim coverage.
"""
import pytest

from satellite_integration import cog
from satellite_integration.conftest import ELSEWHERE_BOUNDS, FOROLE_BOUNDS


class TestBytesToCog:

    def test_writes_a_valid_cog(self, geotiff_bytes, tmp_path):
        info = cog.bytes_to_cog(geotiff_bytes(), tmp_path / "forole.tif")

        assert info.path.exists()
        assert info.size_bytes > 0
        assert info.band_count == 2
        assert info.crs == "EPSG:4326"
        cog.validate_cog(info.path)  # raises if not a valid COG

    def test_band_names_survive_translation(self, geotiff_bytes, tmp_path):
        info = cog.bytes_to_cog(
            geotiff_bytes(band_names=("B4", "B8", "B11")), tmp_path / "s2.tif"
        )
        assert info.band_names == ["B4", "B8", "B11"]

    def test_provenance_tags_are_written_into_the_file(self, geotiff_bytes, tmp_path):
        """Provenance in the raster outlives the database row that describes it."""
        import rasterio

        dest = tmp_path / "tagged.tif"
        cog.bytes_to_cog(
            geotiff_bytes(),
            dest,
            tags={"RANGER_ASSET_ID": "COPERNICUS/S2/XYZ", "RANGER_VALUES": "raw"},
        )
        with rasterio.open(dest) as src:
            tags = src.tags()
        assert tags["RANGER_ASSET_ID"] == "COPERNICUS/S2/XYZ"
        assert tags["RANGER_VALUES"] == "raw"

    def test_html_error_page_is_rejected(self, tmp_path):
        """Earth Engine returns errors with a 200 status.

        Without the magic-number check these bytes would reach rio-cogeo and
        surface as an unreadable GDAL error, or worse, be written to a path a
        row then points at.
        """
        with pytest.raises(cog.CogError, match="not a GeoTIFF"):
            cog.bytes_to_cog(b"<html>Quota exceeded</html>", tmp_path / "bad.tif")

    def test_failure_leaves_no_partial_file(self, tmp_path):
        with pytest.raises(cog.CogError):
            cog.bytes_to_cog(b"not a raster at all", tmp_path / "bad.tif")

        assert list(tmp_path.glob("*")) == []

    def test_existing_file_is_not_silently_overwritten(self, geotiff_bytes, tmp_path):
        """The COG is the expensive artefact — quota was spent to get it."""
        dest = tmp_path / "forole.tif"
        cog.bytes_to_cog(geotiff_bytes(), dest)

        with pytest.raises(cog.CogError, match="already exists"):
            cog.bytes_to_cog(geotiff_bytes(), dest)

        cog.bytes_to_cog(geotiff_bytes(), dest, overwrite=True)  # explicit is fine


class TestOutputProfile:
    """Warnings on the happy path train you to ignore warnings."""

    def test_interleave_is_dropped_for_the_cog_driver(self):
        assert "interleave" not in cog._dst_profile("deflate")

    def test_bands_are_declared_as_measurements_not_colour(self):
        assert cog._dst_profile("deflate")["photometric"] == "minisblack"

    def test_compression_stays_lossless(self):
        assert cog._dst_profile("deflate")["compress"].upper() == "DEFLATE"


class TestBandLabelling:
    """Earth Engine returns selected bands in order but does not name them.

    Without labelling, `SatelliteDataset.bands` ordering becomes an
    undocumented contract that F10.4 would index into blind.
    """

    def test_names_are_written_when_the_count_matches(self, geotiff_bytes, tmp_path):
        info = cog.bytes_to_cog(
            geotiff_bytes(band_names=("x", "y")),  # source names are discarded
            tmp_path / "named.tif",
            band_names=["B4", "B8"],
        )
        assert info.band_names == ["B4", "B8"]

    def test_unnamed_bands_fall_back_to_indices(self, geotiff_bytes, tmp_path):
        """What a raw Earth Engine download looks like."""
        import rasterio

        raw = geotiff_bytes()
        stripped = tmp_path / "src.tif"
        stripped.write_bytes(raw)
        with rasterio.open(stripped, "r+") as dst:
            dst.descriptions = (None, None)

        info = cog.to_cog(stripped, tmp_path / "unnamed.tif")
        assert info.band_names == ["band_1", "band_2"]

    def test_a_count_mismatch_refuses_to_label(self, geotiff_bytes, tmp_path):
        """A mislabelled band is worse than an unlabelled one.

        Wrong-but-authoritative is the failure mode; generic names at least
        announce that nothing is known.
        """
        info = cog.bytes_to_cog(
            geotiff_bytes(band_names=("a", "b")),
            tmp_path / "mismatch.tif",
            band_names=["B2", "B3", "B4", "B8", "B11", "B12", "SCL"],
        )
        assert info.band_names == ["a", "b"]


class TestWarningFilter:

    def test_only_the_photometric_message_is_dropped(self):
        import logging

        noise = cog._PhotometricNoiseFilter()

        def record(message):
            return logging.LogRecord("rasterio._env", logging.WARNING, "", 0,
                                     message, None, None)

        assert not noise.filter(record(
            "CPLE_AppDefined in TIFFReadDirectory:Sum of Photometric "
            "type-related color channels and ExtraSamples doesn't match"
        ))
        assert noise.filter(record("CPLE_AppDefined in something genuinely wrong"))


class TestFootprints:

    def test_bounds_are_read_from_the_file(self, geotiff_bytes, tmp_path):
        info = cog.bytes_to_cog(geotiff_bytes(bounds=FOROLE_BOUNDS), tmp_path / "f.tif")

        for actual, expected in zip(info.bounds_4326, FOROLE_BOUNDS):
            assert actual == pytest.approx(expected, abs=1e-6)

    def test_non_4326_rasters_are_reprojected(self, geotiff_bytes, tmp_path):
        """A UTM download must still yield a 4326 footprint for PostGIS."""
        info = cog.bytes_to_cog(
            geotiff_bytes(crs="EPSG:32637", bounds=(383000, 410000, 383500, 410500)),
            tmp_path / "utm.tif",
        )
        west, south, east, north = info.bounds_4326

        assert info.crs == "EPSG:32637"
        assert 37.9 < west < east < 38.0
        assert 3.6 < south < north < 3.8

    def test_a_footprint_elsewhere_stays_elsewhere(self, geotiff_bytes, tmp_path):
        """Sanity check on the fixture the intersection test depends on."""
        info = cog.bytes_to_cog(
            geotiff_bytes(bounds=ELSEWHERE_BOUNDS), tmp_path / "nbo.tif"
        )
        assert info.bounds_4326[1] < 0  # southern hemisphere; Forole is not


class TestInspect:

    def test_missing_file_raises_cog_error(self, tmp_path):
        with pytest.raises(cog.CogError):
            cog.inspect_cog(tmp_path / "nothing.tif")


class TestStorageLayout:

    def test_asset_ids_are_flattened_not_nested(self):
        """Slashes in an asset ID must not become directories."""
        path = cog.relative_cog_path(
            org_slug="knra",
            dataset_code="s2",
            asset_id="COPERNICUS/S2_SR_HARMONIZED/20260118T073211_T37PCP",
        )
        assert path == (
            "knra/s2/COPERNICUS_S2_SR_HARMONIZED_20260118T073211_T37PCP.tif"
        )
        assert path.count("/") == 2

    def test_same_asset_different_aoi_gets_a_different_path(self):
        """The regression that cost four fetches (F10.3 CP5).

        A file here is the scene CLIPPED to one AOI, not the scene. Boji,
        Gamura, both Dukana wells and Balesa all fall inside Sentinel-2 tile
        T37NCD and were retrieved from the same pass, so they share an asset
        id. Keyed on asset id alone, the second AOI found the first AOI's clip
        on disk and reused it — a valid COG, correct asset id, wrong pixels.

        Only the PostGIS footprint assertion caught it. This test means the
        path itself no longer permits the collision.
        """
        asset = "COPERNICUS/S2_SR_HARMONIZED/20260805T073609_T37NCD"
        boji = cog.relative_cog_path(
            org_slug="knra", dataset_code="s2", asset_id=asset, aoi_key="boji"
        )
        gamura = cog.relative_cog_path(
            org_slug="knra", dataset_code="s2", asset_id=asset, aoi_key="gamura"
        )
        assert boji != gamura
        assert boji.endswith("__boji.tif")
        assert gamura.endswith("__gamura.tif")

    def test_omitting_aoi_key_preserves_the_old_layout(self):
        """Rows written before F10.3 keep resolving to their existing files —
        no migration, no orphans."""
        path = cog.relative_cog_path(
            org_slug="knra", dataset_code="s2", asset_id="COPERNICUS/X/Y"
        )
        assert path == "knra/s2/COPERNICUS_X_Y.tif"

    def test_aoi_key_is_sanitized_too(self):
        path = cog.relative_cog_path(
            org_slug="knra", dataset_code="s2", asset_id="A",
            aoi_key="../../etc/passwd",
        )
        assert ".." not in path
        assert path.count("/") == 2

    def test_traversal_characters_are_stripped(self):
        path = cog.relative_cog_path(
            org_slug="knra", dataset_code="s2", asset_id="../../etc/passwd"
        )
        assert ".." not in path

    def test_absolute_path_stays_under_media_root(self, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        resolved = cog.absolute_cog_path("knra/s2/scene.tif")

        assert resolved == tmp_path / cog.SATELLITE_SUBDIR / "knra/s2/scene.tif"

    def test_absolute_path_refuses_to_escape(self, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        with pytest.raises(cog.CogError, match="outside"):
            cog.absolute_cog_path("../../../etc/passwd")
# ─── RANGER V3 END: cog pipeline tests ───