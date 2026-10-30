# ─── RANGER V3 START: 16-report-marking ───
"""Page marking by weakest tier (F16 fork 7): every page, every time."""
import pytest
from pypdf import PdfReader

from core.models import RadiationLog, SensorLog
from missions.models import Mission
from reports.generate import MARKING, generate_report, page_marking

pytestmark = pytest.mark.django_db

BAND = {t: m["band"] for t, m in MARKING.items()}


@pytest.fixture
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def survey(mission, sensor_log_at, *, pos, rad, n=60):
    """n rows, enough to run the report past one page (exceedance list)."""
    for i in range(n):
        log = sensor_log_at(-1.29 - i * 2e-5, 36.82, mission=mission, radiation=60.0 + i)
        SensorLog.objects.filter(pk=log.pk).update(source=pos)
        RadiationLog.objects.filter(sensor_log=log).update(source=rad)
    mission.status = Mission.Status.COMPLETED
    mission.save(update_fields=["status"])
    return mission


def pages(report, media):
    reader = PdfReader(media / report.pdf_path)
    return reader, [" ".join(p.extract_text().split()) for p in reader.pages]


def test_marking_table():
    assert page_marking("live") == {"band": None, "watermark": None}
    assert page_marking("reported") == {"band": None, "watermark": None}
    assert page_marking("modelled")["watermark"] is None
    assert page_marking("simulated")["watermark"] == "SIMULATED"
    assert "not measurements" in BAND["modelled"] and "not measurements" in BAND["simulated"]


def test_simulated_band_and_watermark_on_every_page(mission, sensor_log_at, media):
    r = generate_report(survey(mission, sensor_log_at, pos="live", rad="simulated"))
    reader, texts = pages(r, media)
    assert len(texts) >= 2
    for i, t in enumerate(texts):
        assert BAND["simulated"] in t, f"page {i + 1}"
        assert "SIMULATED" in t.replace(BAND["simulated"], ""), f"watermark page {i + 1}"
    assert "provenance-simulated" in reader.metadata.get("/Keywords", "")


def test_modelled_band_every_page_no_watermark(mission, sensor_log_at, media):
    r = generate_report(survey(mission, sensor_log_at, pos="modelled", rad="modelled"))
    reader, texts = pages(r, media)
    for i, t in enumerate(texts):
        assert BAND["modelled"] in t, f"page {i + 1}"
    assert not any(BAND["simulated"] in t for t in texts)
    assert "provenance-modelled" in reader.metadata.get("/Keywords", "")


def test_live_has_no_band(mission, sensor_log_at, media):
    r = generate_report(survey(mission, sensor_log_at, pos="live", rad="live", n=3))
    reader, texts = pages(r, media)
    for t in texts:
        assert not any(b in t for b in BAND.values())
    assert "provenance-live" in reader.metadata.get("/Keywords", "")


def test_one_simulated_reading_marks_the_whole_report(mission, sensor_log_at, media):
    survey(mission, sensor_log_at, pos="live", rad="live", n=5)
    log = SensorLog.objects.filter(mission=mission).first()
    RadiationLog.objects.filter(sensor_log=log).update(source="simulated")
    r = generate_report(mission)
    _, texts = pages(r, media)
    assert all(BAND["simulated"] in t for t in texts)
# ─── RANGER V3 END: 16-report-marking ───
