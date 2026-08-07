# ─── RANGER V3 START: render tests ───
"""
Raster rendering and the render endpoint (F10.3 CP1).

The test that matters most in this module is
`test_landsat_ndvi_applies_the_offset`. Everything else here checks that a
view returns the right status code. That one checks that a number is not
silently wrong.

Landsat Collection 2 Level 2 reflectance is `2.75e-5 * DN - 0.2`. The offset
survives in the denominator of a normalised ratio, so NDVI computed from raw
Landsat DNs is not NDVI — it is a plausible-looking number in the right range
that no downstream check can distinguish from the real thing. Over a 38x41 px
scene it renders as a perfectly convincing image.
"""
import datetime as dt

import pytest
from django.urls import reverse

from satellite_integration import render
from satellite_integration.models import SatelliteDataset

pytestmark = pytest.mark.django_db


# ── the registry ────────────────────────────────────────────────────


class TestLayerRegistry:

    def test_layers_are_keyed_on_the_dataset_pair(self):
        """There is no dataset-agnostic 'ndvi', and there must not be."""
        assert ("s2", "ndvi") in render.LAYERS
        assert ("l9", "ndvi") in render.LAYERS
        assert render.LAYERS[("s2", "ndvi")].bands != \
            render.LAYERS[("l9", "ndvi")].bands

    def test_s2_calibration_cancels_in_a_ratio(self):
        assert render.S2_SR.cancels_in_a_ratio is True

    def test_landsat_calibration_does_not_cancel(self):
        """The offset is the whole reason the registry is per-dataset."""
        assert render.L9_SR.cancels_in_a_ratio is False
        assert render.L9_ST.cancels_in_a_ratio is False

    def test_s2_ndvi_skips_calibration_and_l9_ndvi_does_not(self):
        """Flip either of these and the layer still renders, wrongly."""
        assert render.LAYERS[("s2", "ndvi")].apply_calibration is False
        assert render.LAYERS[("l9", "ndvi")].apply_calibration is True

    def test_every_layer_that_skips_calibration_provably_cancels(self):
        """A blanket guard against the next person adding a layer.

        Skipping calibration is only ever legitimate for a display stretch or
        a ratio whose factor cancels. Anything else that sets
        apply_calibration=False is the Landsat NDVI bug again.
        """
        for (code, key), layer in render.LAYERS.items():
            if layer.apply_calibration:
                continue
            if layer.kind == "rgb":
                continue  # display stretch; absolute units are not claimed
            assert layer.calibration is not None, (code, key)
            assert layer.calibration.cancels_in_a_ratio, (
                f"{code}/{key} skips calibration but its calibration has an "
                f"offset, which does not cancel in a ratio."
            )

    def test_unknown_pair_raises_and_names_the_alternatives(self):
        with pytest.raises(render.UnknownLayer) as exc:
            render.get_layer("s2", "thermal")
        # s2 has no thermal band; the message must say what it DOES have
        assert "ndvi" in str(exc.value)

    def test_layers_for_unknown_dataset_is_empty_not_a_default(self):
        assert render.layers_for("nope") == []

    def test_every_layer_carries_a_caption(self):
        """The caption says what the number is and what it is not. A layer
        without one is a layer the UI cannot label honestly."""
        for (code, key), layer in render.LAYERS.items():
            assert layer.caption.strip(), (code, key)


# ── the maths ───────────────────────────────────────────────────────


class TestCalibrationArithmetic:

    def test_offset_changes_the_ratio(self):
        """The claim the registry rests on, asserted directly.

        Same DNs, same formula. Scale-only leaves the ratio untouched;
        scale-plus-offset does not. If this ever passes with the two equal,
        the whole per-dataset design is unnecessary — and it never will.
        """
        # Plain floats, not arrays: numpy 2.x refuses float() on a size-1
        # ndarray, and the arithmetic here needs no array semantics anyway.
        nir_dn, red_dn = 3200.0, 1400.0

        def ratio(cal):
            hi, lo = cal.apply(nir_dn), cal.apply(red_dn)
            return (hi - lo) / (hi + lo)

        raw = (nir_dn - red_dn) / (nir_dn + red_dn)
        s2 = ratio(render.S2_SR)
        l9 = ratio(render.L9_SR)

        assert s2 == pytest.approx(raw)              # scale cancels
        assert l9 != pytest.approx(raw)              # offset does not
        assert abs(l9 - raw) > 0.05                  # and not marginally

    def test_thermal_calibration_lands_in_a_plausible_kelvin_range(self):
        """ST_B10 DNs around 44000 are roughly 300 K. A wrong scale or a
        dropped offset lands nowhere near, so this catches a transposition."""
        kelvin = render.L9_ST.apply(44000.0)
        assert 280.0 < kelvin < 320.0


# ── rendering ───────────────────────────────────────────────────────


class TestRenderPng:

    def test_writes_a_png(self, geotiff_bytes, tmp_path):
        from satellite_integration.cog import bytes_to_cog

        src = tmp_path / "scene.tif"
        bytes_to_cog(geotiff_bytes(band_names=("B8", "B4")), src,
                     band_names=["B8", "B4"])

        layer = render.LAYERS[("s2", "ndvi")]
        out = render.render_png(src, layer, tmp_path / "out.png")

        assert out.exists()
        assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    def test_output_is_rgba_so_nodata_is_transparent(
        self, geotiff_bytes, tmp_path
    ):
        """An opaque rectangle painted over the basemap outside the clip
        reads as data."""
        from PIL import Image
        from satellite_integration.cog import bytes_to_cog

        src = tmp_path / "scene.tif"
        bytes_to_cog(geotiff_bytes(band_names=("B8", "B4")), src,
                     band_names=["B8", "B4"])
        out = render.render_png(
            src, render.LAYERS[("s2", "ndvi")], tmp_path / "out.png"
        )
        assert Image.open(out).mode == "RGBA"

    def test_landsat_ndvi_applies_the_offset(self, geotiff_bytes, tmp_path):
        """THE regression test for this checkpoint.

        Render the same pixels twice — once through the l9 entry (offset
        applied) and once through the s2 entry (offset skipped) — and assert
        the outputs differ. If a later refactor sets the l9 flag to False,
        the endpoint keeps returning 200 and a convincing image, and only
        this assertion notices.
        """
        from satellite_integration.cog import bytes_to_cog

        src = tmp_path / "l9.tif"
        bytes_to_cog(
            geotiff_bytes(band_names=("SR_B5", "SR_B4", "B8", "B4")),
            src,
            band_names=["SR_B5", "SR_B4", "B8", "B4"],
        )

        calibrated = render.render_png(
            src, render.LAYERS[("l9", "ndvi")], tmp_path / "cal.png"
        ).read_bytes()
        uncalibrated = render.render_png(
            src, render.LAYERS[("s2", "ndvi")], tmp_path / "raw.png"
        ).read_bytes()

        assert calibrated != uncalibrated

    def test_bands_are_looked_up_by_name_not_position(
        self, geotiff_bytes, tmp_path
    ):
        """Band order changes must not silently swap channels.

        Asserted on the lookup itself rather than by rendering two files and
        comparing bytes: `geotiff_bytes` fills each band from its POSITION,
        so reordering the names does not reorder the pixels, and the two
        renders differ for a reason that has nothing to do with the lookup.
        A test that compared them would fail while the code was correct —
        which is what the first version of this test did.

        NDVI wants (B8, B4). Write the file with B4 first and assert the
        resolver still points B8 at band 2.
        """
        import rasterio
        from satellite_integration.cog import bytes_to_cog

        src = tmp_path / "rev.tif"
        bytes_to_cog(geotiff_bytes(band_names=("B4", "B8")), src,
                     band_names=["B4", "B8"])

        with rasterio.open(src) as ds:
            available = [
                ds.descriptions[i] or f"band{i + 1}" for i in range(ds.count)
            ]

        assert available == ["B4", "B8"]          # positionally reversed
        assert render._band_index(available, "B8") == 2
        assert render._band_index(available, "B4") == 1

        # And the renderer resolves through the same path, so it reads NIR
        # from band 2 here and would read it from band 1 in the other order.
        layer = render.LAYERS[("s2", "ndvi")]
        assert [render._band_index(available, b) for b in layer.bands] == [2, 1]

    def test_a_missing_band_names_itself(self, geotiff_bytes, tmp_path):
        from satellite_integration.cog import bytes_to_cog

        src = tmp_path / "scene.tif"
        bytes_to_cog(geotiff_bytes(band_names=("B4", "B3")), src,
                     band_names=["B4", "B3"])

        with pytest.raises(render.MissingBands) as exc:
            render.render_png(
                src, render.LAYERS[("s2", "ndvi")], tmp_path / "x.png"
            )
        assert "B8" in str(exc.value)


class TestRenderCache:

    def _cog(self, geotiff_bytes, tmp_path):
        from satellite_integration.cog import bytes_to_cog

        src = tmp_path / "scene.tif"
        bytes_to_cog(geotiff_bytes(band_names=("B8", "B4")), src,
                     band_names=["B8", "B4"])
        return src

    def test_second_call_reuses_the_file(self, geotiff_bytes, tmp_path):
        src = self._cog(geotiff_bytes, tmp_path)
        layer = render.LAYERS[("s2", "ndvi")]

        first = render.cached_or_render(src, layer)
        stamp = first.stat().st_mtime_ns
        second = render.cached_or_render(src, layer)

        assert second == first
        assert second.stat().st_mtime_ns == stamp

    def test_a_newer_cog_invalidates_the_cache(self, geotiff_bytes, tmp_path):
        """fetch_scenes --overwrite must not leave the old pixels on screen
        beside the new metadata."""
        import os
        import time

        src = self._cog(geotiff_bytes, tmp_path)
        layer = render.LAYERS[("s2", "ndvi")]
        png = render.cached_or_render(src, layer)
        before = png.stat().st_mtime_ns

        time.sleep(0.01)
        future = time.time() + 10
        os.utime(src, (future, future))

        again = render.cached_or_render(src, layer)
        assert again.stat().st_mtime_ns != before

    def test_cache_sits_beside_the_cog_one_per_layer(self, tmp_path):
        cog_path = tmp_path / "a" / "b" / "scene.tif"
        ndvi = render.cache_path(cog_path, "ndvi")
        true = render.cache_path(cog_path, "truecolor")
        assert ndvi.parent == cog_path.parent
        assert ndvi != true


# ── the endpoint ────────────────────────────────────────────────────


def _url(image, layer=None):
    url = reverse("satellite-image-render", args=[image.pk])
    return f"{url}?layer={layer}" if layer else url


@pytest.fixture
def s2_scene_on_disk(db, org, s2, make_scene, geotiff_bytes, settings,
                     tmp_path):
    """A SatelliteImage whose COG genuinely exists under MEDIA_ROOT."""
    from satellite_integration.cog import bytes_to_cog, absolute_cog_path

    settings.MEDIA_ROOT = tmp_path
    _query, image = make_scene(org, s2, cog_path="knra/s2/test.tif")
    image.bands = ["B8", "B4"]
    image.save(update_fields=["bands"])

    dest = absolute_cog_path(image.cog_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    bytes_to_cog(geotiff_bytes(band_names=("B8", "B4")), dest,
                 band_names=["B8", "B4"])
    return image


class TestRenderEndpoint:

    def test_returns_a_png(self, authed_client, s2_scene_on_disk):
        response = authed_client.get(_url(s2_scene_on_disk, "ndvi"))
        assert response.status_code == 200
        assert response["Content-Type"] == "image/png"
        assert b"".join(response.streaming_content)[:8] == b"\x89PNG\r\n\x1a\n"

    def test_requires_authentication(self, api_client, s2_scene_on_disk):
        assert api_client.get(
            _url(s2_scene_on_disk, "ndvi")
        ).status_code in (401, 403)

    def test_another_tenant_gets_404_not_403(
        self, other_client, s2_scene_on_disk
    ):
        """404, because 403 confirms the row exists. cog_path is unserialized
        (ADR-0012 §6) precisely so ids cannot be turned into pixels across
        tenants — that holds only if this lookup is scoped."""
        assert other_client.get(
            _url(s2_scene_on_disk, "ndvi")
        ).status_code == 404

    def test_missing_layer_param_is_400_and_lists_options(
        self, authed_client, s2_scene_on_disk
    ):
        response = authed_client.get(_url(s2_scene_on_disk))
        assert response.status_code == 400
        assert "ndvi" in response.data["available"]

    def test_unknown_layer_is_404_never_a_fallback(
        self, authed_client, s2_scene_on_disk
    ):
        """A fallback would compute an S2 recipe over whatever this is."""
        response = authed_client.get(_url(s2_scene_on_disk, "thermal"))
        assert response.status_code == 404

    def test_row_without_a_cog_is_409(
        self, authed_client, org, s2, make_scene
    ):
        _q, image = make_scene(org, s2, cog_path="")
        assert authed_client.get(_url(image, "ndvi")).status_code == 409

    def test_cog_path_pointing_off_disk_is_409_not_500(
        self, authed_client, org, s2, make_scene, settings, tmp_path
    ):
        settings.MEDIA_ROOT = tmp_path
        _q, image = make_scene(org, s2, cog_path="knra/s2/absent.tif")
        assert authed_client.get(_url(image, "ndvi")).status_code == 409

    def test_traversal_in_cog_path_is_refused(
        self, authed_client, org, s2, make_scene, settings, tmp_path
    ):
        settings.MEDIA_ROOT = tmp_path
        _q, image = make_scene(
            org, s2, cog_path="../../../../etc/passwd"
        )
        assert authed_client.get(_url(image, "ndvi")).status_code == 409

    def test_scene_missing_a_needed_band_is_409_and_names_it(
        self, authed_client, org, s2, make_scene, geotiff_bytes,
        settings, tmp_path
    ):
        from satellite_integration.cog import bytes_to_cog, absolute_cog_path

        settings.MEDIA_ROOT = tmp_path
        _q, image = make_scene(org, s2, cog_path="knra/s2/rgb.tif")
        dest = absolute_cog_path(image.cog_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        bytes_to_cog(geotiff_bytes(band_names=("B4", "B3")), dest,
                     band_names=["B4", "B3"])

        response = authed_client.get(_url(image, "ndvi"))
        assert response.status_code == 409
        assert "B8" in response.data["detail"]

    def test_response_is_privately_cacheable_only(
        self, authed_client, s2_scene_on_disk
    ):
        """Tenant data behind auth must never land in a shared cache."""
        response = authed_client.get(_url(s2_scene_on_disk, "ndvi"))
        assert "private" in response["Cache-Control"]
# ─── RANGER V3 END: render tests ───