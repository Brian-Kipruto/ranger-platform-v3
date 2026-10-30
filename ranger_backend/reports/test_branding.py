# ─── RANGER V3 START: 16-report-branding ───
"""Tenant branding (7b step 4): untrusted inputs, fixed provenance colours."""
import io
from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from pypdf import PdfReader

from core.models import RadiationLog, SensorLog
from missions.models import Mission
from reports import branding as b
from reports import generate as gen

pytestmark = pytest.mark.django_db


def png_bytes(w, h, colour=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), colour).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


@pytest.fixture
def capture(monkeypatch):
    """Record the HTML each report is rendered from."""
    seen = []
    real = gen.render_pdf

    def spy(html, *a, **k):
        seen.append(html)
        return real(html, *a, **k)
    monkeypatch.setattr(gen, "render_pdf", spy)
    return seen


def done(mission, sensor_log_at, tier="modelled"):
    log = sensor_log_at(-1.29, 36.82, mission=mission, radiation=50.0)
    SensorLog.objects.filter(pk=log.pk).update(source=tier)
    RadiationLog.objects.filter(sensor_log=log).update(source=tier)
    mission.status = Mission.Status.COMPLETED
    mission.save(update_fields=["status"])
    return mission


class TestAccent:
    @pytest.mark.parametrize("value", [
        "red;}x", "#12345", "#12345g", "", None,
        "url(x)", "#abc", "0ea5e9",
    ])
    def test_anything_but_rrggbb_is_replaced(self, value):
        assert b.accent(SimpleNamespace(theme_color=value)) == b.DEFAULT_ACCENT

    def test_valid_hex_kept_and_normalised(self):
        assert b.accent(SimpleNamespace(theme_color="#A1B2C3")) == "#a1b2c3"

    def test_injection_never_reaches_the_html(self, mission, sensor_log_at, media, capture):
        org = mission.organization
        org.theme_color = "red;}x"   # max_length=7 still allows a payload
        org.save(update_fields=["theme_color"])
        gen.generate_report(done(mission, sensor_log_at))
        assert "red;}" not in capture[-1]
        assert b.DEFAULT_ACCENT in capture[-1]


class TestLogo:
    def test_logo_embedded_and_downscaled(self, mission, sensor_log_at, media, capture):
        org = mission.organization
        org.logo = SimpleUploadedFile("big.png", png_bytes(3000, 1000), content_type="image/png")
        org.save()
        r = gen.generate_report(done(mission, sensor_log_at))
        lg = b.logo(org)
        assert lg["width"] <= b.LOGO_MAX_PX[0] and lg["height"] <= b.LOGO_MAX_PX[1]
        assert r.summary["branding"]["logo"] is True
        assert lg["src"] in capture[-1]
        images = sum(len(p.images) for p in PdfReader(media / r.pdf_path).pages)
        assert images >= 3   # logo + detail map + colour bar

    def test_not_an_image_falls_back(self, mission, sensor_log_at, media):
        org = mission.organization
        org.logo = SimpleUploadedFile("evil.png", b"<script>not an image</script>")
        org.save()
        assert b.logo(org) is None
        r = gen.generate_report(done(mission, sensor_log_at))
        assert r.summary["branding"]["logo"] is False
        assert (media / r.pdf_path).exists()

    @pytest.mark.parametrize("weasyprint_flag", [False, True])
    def test_truncated_image_falls_back(self, mission, media, monkeypatch, weasyprint_flag):
        # WeasyPrint sets this process-wide on import; once any report has
        # rendered, a truncated logo decodes silently. Pin both states so the
        # test cannot pass or fail by test order.
        from PIL import ImageFile
        monkeypatch.setattr(ImageFile, "LOAD_TRUNCATED_IMAGES", weasyprint_flag)
        org = mission.organization
        org.logo = SimpleUploadedFile("cut.png", png_bytes(400, 200)[:200])
        org.save()
        assert b.logo(org) is None

    def test_missing_file_falls_back(self, mission, media):
        org = mission.organization
        org.logo.name = "org_logos/gone.png"
        assert b.logo(org) is None

    def test_no_logo(self, mission):
        assert b.logo(mission.organization) is None


class TestPlacement:
    def test_org_name_and_producer_printed(self, mission, sensor_log_at, media):
        r = gen.generate_report(done(mission, sensor_log_at))
        text = " ".join(PdfReader(media / r.pdf_path).pages[0].extract_text().split())
        assert mission.organization.name in text
        assert b.PRODUCER in text

    @pytest.mark.parametrize("tier,band_bg", [("modelled", "#fff1cc"), ("simulated", "#ffe3e3")])
    def test_tenant_accent_never_recolours_the_band(self, mission, sensor_log_at, media, capture,
                                                   tier, band_bg):
        org = mission.organization
        org.theme_color = "#ff0000"
        org.save(update_fields=["theme_color"])
        gen.generate_report(done(mission, sensor_log_at, tier))
        html = capture[-1]
        top = html[html.index("@top-center"):html.index("}", html.index("@top-center"))]
        assert band_bg in top and "#ff0000" not in top
# ─── RANGER V3 END: 16-report-branding ───
