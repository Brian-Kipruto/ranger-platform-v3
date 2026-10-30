# ─── RANGER V3 START: 16-report-map ───
"""Survey map figures (F16 fork 6)."""
import io
import math
from datetime import datetime, timedelta, timezone
import pytest
from PIL import Image

from core.geo import polygon_from_bbox
from reports import map as rmap
from reports.generate import generate_report
from reports.conftest import FOROLE_FOOTPRINT

FOROLE = (37.9668, 3.7160, 37.9678, 3.7175)
T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def pt(lon, lat, *, t=0, source="live", dose=None, dose_src=None, cpm=None,
       pm25=None, pm_src=None):
    return {"lon": lon, "lat": lat, "timestamp": T0 + timedelta(seconds=t),
            "source": source,
            "dose_rate_usvh": dose, "cpm": cpm, "radiation_source": dose_src,
            "pm25": pm25, "air_quality_source": pm_src}


def grid(source="live", n=5, **kw):
    # ~40 m apart, 20 s apart: 2 m/s, a plausible rover track.
    return [pt(37.9668 + i * 2e-4, 3.7160 + i * 3e-4, t=20 * i, source=source, **kw)
            for i in range(n)]


def png(fig):
    return Image.open(io.BytesIO(fig.png)).convert("RGB")


class TestExtent:
    @pytest.mark.parametrize("lat", [0.0, 3.7, 34.0])
    def test_equal_metres_per_pixel_on_both_axes(self, lat):
        # Without the cos(lat) term a Rabat map is stretched ~20% east-west.
        e = rmap.Extent(-6.85, lat, -6.84, lat + 0.01)
        w, h = e.fit((1800, 1150))
        assert e.width_m / w == pytest.approx(e.height_m / h, rel=0.01)

    def test_ground_width_independent_of_extent(self):
        # 0.01 deg of longitude at 34 N is 0.01 * 111320 * cos(34 deg) m,
        # computed here without Extent, so the check is not circular.
        e = rmap.Extent(-6.85, 33.995, -6.84, 34.005)
        expected = 0.01 * 111_320 * math.cos(math.radians(34.0))
        assert e.width_m == pytest.approx(expected, rel=1e-3)
        w, h = e.fit((1000, 1000))
        assert w / h == pytest.approx(math.cos(math.radians(34.0)), rel=0.01)

    def test_corners_map_to_pixel_corners(self):
        e = rmap.Extent(*FOROLE)
        assert e.to_px(100, 200, e.west, e.north) == (0, 0)
        assert e.to_px(100, 200, e.east, e.south) == pytest.approx((100, 200))

    def test_single_point_gets_a_frame(self):
        e = rmap.bbox_of([37.0], [3.0]).padded(0.1, 40.0)
        assert e.width_m >= 40 and e.height_m >= 40


class TestDetail:
    def test_no_track_through_modelled_positions(self):
        fig = rmap.detail_figure(grid("modelled", dose=0.1, dose_src="modelled"))
        assert fig.meta["track_drawn"] is False

    def test_track_for_live_positions(self):
        fig = rmap.detail_figure(grid("live", dose=0.1, dose_src="simulated"))
        assert fig.meta["track_drawn"] is True

    def test_plausible_track_is_one_segment(self):
        fig = rmap.detail_figure(grid())
        assert fig.meta["track_breaks"] == 0

    def test_track_breaks_at_a_position_jump(self):
        # ~1.1 km in one second between fixes 3 and 4: not a route.
        pts = grid(n=3) + [pt(37.9768, 3.7260, t=41), pt(37.9770, 3.7262, t=61)]
        assert rmap.detail_figure(pts).meta["track_breaks"] == 1

    def test_fast_sim_step_is_not_a_break(self):
        # nmea_sim's route walker: ~10 m per 1 Hz fix (mission 12). Not a jump.
        pts = [pt(36.8133 + i * 9e-5, -1.2886, t=i) for i in range(20)]
        assert rmap.detail_figure(pts).meta["track_breaks"] == 0

    def test_track_breaks_at_a_time_gap(self):
        # Same place, 10 minutes later: the robot did not drive in between.
        pts = grid(n=3) + [pt(37.9672, 3.7166, t=640)]
        assert rmap.detail_figure(pts).meta["track_breaks"] == 1

    def test_one_modelled_position_suppresses_the_track(self):
        pts = grid("live") + [pt(37.967, 3.717, source="modelled")]
        assert rmap.detail_figure(pts).meta["track_drawn"] is False

    def test_colours_by_dose_before_pm(self):
        fig = rmap.detail_figure(grid(dose=0.1, dose_src="live", pm25=10.0, pm_src="live"))
        assert fig.meta["colour_by"]["label"] == "Dose rate"

    def test_colours_by_cpm_when_dose_is_null(self):
        # The uncalibrated sim Geiger: CPM present, dose null. Map radiation,
        # not PM.
        fig = rmap.detail_figure(grid(dose_src="simulated", cpm=30.0,
                                      pm25=10.0, pm_src="simulated"))
        assert fig.meta["colour_by"]["label"] == "Count rate"

    def test_never_colours_by_modelled_cpm(self):
        fig = rmap.detail_figure(grid("modelled", dose_src="modelled", cpm=46.8))
        assert fig.meta["colour_by"] is None

    def test_falls_back_to_pm(self):
        fig = rmap.detail_figure(grid(pm25=10.0, pm_src="simulated"))
        c = fig.meta["colour_by"]
        assert c["label"] == "PM2.5" and c["sources"] == ["simulated"]

    def test_nothing_to_colour(self):
        assert rmap.detail_figure(grid()).meta["colour_by"] is None

    def test_domain_is_p5_p95(self):
        vals = [float(v) for v in range(101)]  # 0..100 -> P5=5, P95=95
        pts = [pt(37.9668 + i * 1e-6, 3.716, t=i, dose=v, dose_src="live")
               for i, v in enumerate(vals)]
        c = rmap.detail_figure(pts).meta["colour_by"]
        assert c["domain"] == pytest.approx([5.0, 95.0])
        assert (c["data_min"], c["data_max"]) == (0.0, 100.0)

    def test_highest_value_drawn_on_top(self):
        # Two readings at the SAME spot: the pixel there must be the high
        # colour, or an anomaly can be buried under background points.
        others = [pt(37.9668 + i * 1e-4, 3.7160, dose=0.5, dose_src="live") for i in range(10)]
        hi = pt(37.9673, 3.7168, dose=1.0, dose_src="live")
        lo = pt(37.9673, 3.7168, dose=0.0, dose_src="live")
        fig = rmap.detail_figure(others + [hi, lo])  # low listed LAST
        ext = rmap.Extent(*fig.meta["extent"])
        x, y = ext.to_px(fig.width, fig.height, 37.9673, 3.7168)
        r, g, b = png(fig).getpixel((round(x), round(y)))
        # Markers are 230/255 alpha, so the top colour blends slightly with
        # what is under it. Yellow on top reads ~(235, 209, 42); purple on top
        # reads ~(80, 20, 80). Assert which one won, not an exact value.
        assert r > 200 and g > 170 and b < 100, (r, g, b)

    def test_no_points(self):
        assert rmap.detail_figure([]).omitted

    def test_aoi_included_in_extent(self):
        aoi = polygon_from_bbox(37.960, 3.710, 37.975, 3.725)
        fig = rmap.detail_figure(grid(), aoi=aoi)
        w, s, e, n = fig.meta["extent"]
        assert w < 37.960 and e > 37.975 and s < 3.710 and n > 3.725


pytestmark_db = pytest.mark.django_db


@pytest.fixture
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


@pytest.fixture
def scene_on_disk(media, geotiff_bytes, make_scene, s2, org):
    """A real 3-band COG on disk, linked to a mission of `org`."""
    from satellite_integration import cog

    def _make(mission, *, dataset=None, rel="knra/s2/forole.tif", write=True, organization=None):
        dataset = dataset or s2
        if write:
            raw = geotiff_bytes(bounds=FOROLE_FOOTPRINT, width=112, height=119,
                                band_names=("B4", "B3", "B2") if dataset.code == "s2"
                                else ("SR_B4", "SR_B3", "SR_B2"))
            cog.bytes_to_cog(raw, cog.absolute_cog_path(rel),
                             band_names=list(("B4", "B3", "B2") if dataset.code == "s2"
                                             else ("SR_B4", "SR_B3", "SR_B2")))
        query, image = make_scene(organization or mission.organization, dataset, cog_path=rel)
        query.mission = mission
        query.save(update_fields=["mission"])
        return image
    return _make


@pytest.mark.django_db
class TestScene:
    def test_pick_prefers_finer_resolution(self, mission, scene_on_disk, l9):
        scene_on_disk(mission, dataset=l9, rel="knra/l9/f.tif")
        s2img = scene_on_disk(mission, rel="knra/s2/f.tif")
        assert rmap.pick_scene(mission).pk == s2img.pk

    def test_pick_ignores_another_orgs_scene(self, mission, scene_on_disk, other_org):
        scene_on_disk(mission, organization=other_org)
        assert rmap.pick_scene(mission) is None

    def test_pick_ignores_empty_cog_path(self, mission, scene_on_disk):
        scene_on_disk(mission, rel="", write=False)
        assert rmap.pick_scene(mission) is None

    def test_context_renders_with_cog_bounds_and_survey_box(self, mission, scene_on_disk):
        scene_on_disk(mission)
        fig = rmap.context_figure(mission, rmap.Extent(*FOROLE))
        assert fig.png and not fig.omitted
        assert fig.meta["bounds"] == pytest.approx(list(FOROLE_FOOTPRINT), abs=1e-6)
        assert fig.meta["attribution"].startswith("Contains modified Copernicus Sentinel data")
        assert "NOT calibrated reflectance" in fig.meta["layer_caption"]
        im = png(fig)
        ext = rmap.Extent(*fig.meta["bounds"])
        x0, y0 = ext.to_px(fig.width, fig.height, FOROLE[0], FOROLE[3])
        assert im.getpixel((round(x0) + 1, round((y0 + ext.to_px(fig.width, fig.height, FOROLE[0], FOROLE[1])[1]) / 2))) \
            == rmap.OUTLINE

    def test_ground_aspect_kept(self, mission, scene_on_disk):
        scene_on_disk(mission)
        fig = rmap.context_figure(mission, rmap.Extent(*FOROLE))
        ext = rmap.Extent(*fig.meta["bounds"])
        assert ext.width_m / fig.width == pytest.approx(ext.height_m / fig.height, rel=0.01)
        # ...and the scene FILLS that canvas: no white margin where a
        # mis-sized resize would leave the canvas background showing.
        im = png(fig)
        for x, y in [(5, fig.height - 5), (fig.width // 2, fig.height - 5), (5, 5)]:
            assert im.getpixel((x, y)) != (255, 255, 255), (x, y)

    def test_missing_cog_file_is_omitted_not_fatal(self, mission, scene_on_disk):
        scene_on_disk(mission, write=False)
        fig = rmap.context_figure(mission, rmap.Extent(*FOROLE))
        assert fig.png is None and "could not be rendered" in fig.omitted

    def test_no_scene(self, mission):
        assert "No satellite scene" in rmap.context_figure(mission, rmap.Extent(*FOROLE)).omitted


@pytest.mark.django_db
class TestInReport:
    def _done(self, mission, sensor_log_at):
        from missions.models import Mission
        for i in range(3):
            sensor_log_at(3.7165 + i * 1e-4, 37.9672, mission=mission, radiation=100.0 * (i + 1))
        mission.status = Mission.Status.COMPLETED
        mission.save(update_fields=["status"])
        return mission

    def test_report_with_scene_embeds_two_figures(self, mission, sensor_log_at, scene_on_disk, media):
        from pypdf import PdfReader
        scene_on_disk(mission)
        r = generate_report(self._done(mission, sensor_log_at))
        assert r.summary["map"]["context"]["dataset"] == "s2"
        assert r.summary["map"]["detail"]["n_points"] == 3
        images = sum(len(p.images) for p in PdfReader(media / r.pdf_path).pages)
        assert images >= 3  # detail, colour bar, context

    def test_broken_scene_still_produces_a_report(self, mission, sensor_log_at, scene_on_disk, media):
        scene_on_disk(mission, write=False)
        r = generate_report(self._done(mission, sensor_log_at))
        assert "could not be rendered" in r.summary["map"]["context"]["omitted"]
        assert (media / r.pdf_path).exists()
# ─── RANGER V3 END: 16-report-map ───
