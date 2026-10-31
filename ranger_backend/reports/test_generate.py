# ─── RANGER V3 START: 16-report-generate ───
"""generate_report: refusals, atomicity, hashes, the embedded CSV, the command."""
import csv
import hashlib
import io
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from pypdf import PdfReader

from core.exports import CSV_FIELDNAMES
from core.models import RadiationLog, SensorLog
from core.tests import EXPECTED_CSV_HEADER
from missions.models import Mission
from reports import generate as gen
from reports.generate import ReportError, generate_report
from reports.models import Report

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


@pytest.fixture
def done(mission):
    mission.status = Mission.Status.COMPLETED
    mission.save(update_fields=["status"])
    return mission


@pytest.fixture
def surveyed(done, sensor_log_at):
    """Three rows: live positions, simulated radiation 100/200/300 CPM."""
    for i, cpm in enumerate((100.0, 200.0, 300.0)):
        log = sensor_log_at(-1.29 - i * 1e-4, 36.82, mission=done,
                            timestamp=timezone.now(), radiation=cpm)
        SensorLog.objects.filter(pk=log.pk).update(
            source="live", provenance_note="bench run")
    return done


def pdf_files(root: Path):
    return [p for p in root.rglob("*") if p.is_file()]


def attachment(report, media):
    reader = PdfReader(media / report.pdf_path)
    (name, [data]), = reader.attachments.items()
    return name, data


class TestRefusals:
    def test_not_completed(self, mission, sensor_log_at, media):
        sensor_log_at(-1.29, 36.82, mission=mission, radiation=10.0)
        with pytest.raises(ReportError, match="COMPLETED"):
            generate_report(mission)
        assert Report.objects.count() == 0 and pdf_files(media) == []

    def test_no_rows(self, done, media):
        with pytest.raises(ReportError, match="no sensor logs"):
            generate_report(done)
        assert Report.objects.count() == 0 and pdf_files(media) == []

    def test_foreign_org_rows(self, surveyed, sensor_log_at, other_robot, media):
        sensor_log_at(-1.29, 36.82, robot=other_robot, mission=surveyed, radiation=5.0)
        with pytest.raises(ReportError, match="outside its organization"):
            generate_report(surveyed)
        assert Report.objects.count() == 0 and pdf_files(media) == []


class TestGenerate:
    def test_row_and_file(self, surveyed, media):
        r = generate_report(surveyed)
        pdf = media / r.pdf_path
        assert pdf.read_bytes()[:5] == b"%PDF-"
        assert hashlib.sha256(pdf.read_bytes()).hexdigest() == r.pdf_sha256
        assert r.organization_id == surveyed.organization_id
        assert r.row_count == 3
        assert r.weakest_source == "simulated"   # live positions, sim radiation
        assert r.format_version == gen.REPORT_FORMAT_VERSION

    def test_embedded_csv_is_the_mission_and_matches_its_hash(self, surveyed, media):
        r = generate_report(surveyed)
        name, data = attachment(r, media)
        assert name.endswith("-data.csv")
        assert hashlib.sha256(data).hexdigest() == r.csv_sha256
        rows = list(csv.reader(io.StringIO(data.decode("utf-8"))))
        assert rows[0] == EXPECTED_CSV_HEADER == CSV_FIELDNAMES
        assert sorted(float(x[rows[0].index("radiation_value")]) for x in rows[1:]) \
            == [100.0, 200.0, 300.0]
        assert {x[rows[0].index("radiation_source")] for x in rows[1:]} == {"simulated"}

    def test_pdf_prints_the_stats_and_weakest(self, surveyed, media):
        r = generate_report(surveyed)
        text = "\n".join(p.extract_text() for p in PdfReader(media / r.pdf_path).pages)
        assert "SIMULATED" in text
        assert "200.0" in text          # mean CPM, 1 decimal
        assert "bench run" in text      # citation
        assert r.csv_sha256 in text.replace("\n", "")

    def test_regenerating_makes_a_new_report(self, surveyed, media):
        a = generate_report(surveyed)
        b = generate_report(surveyed)
        assert a.pk != b.pk and a.pdf_path != b.pdf_path
        assert (media / a.pdf_path).exists() and (media / b.pdf_path).exists()

    def test_same_second_identical_pdfs_get_distinct_files(self, surveyed, media, monkeypatch):
        # WeasyPrint is byte-deterministic within one wall-clock second. Two
        # generations then had the same bytes, sha, name: the second
        # overwrote the first and two rows shared one file. Frozen here.
        import datetime as dt
        fixed = dt.datetime(2026, 10, 30, 12, 0, 0, tzinfo=dt.timezone.utc)
        monkeypatch.setattr(gen.timezone, "now", lambda: fixed)
        monkeypatch.setattr(gen, "render_pdf", lambda *a, **k: b"%PDF-1.7 same bytes")
        a = generate_report(surveyed)
        b = generate_report(surveyed)
        assert a.pdf_path != b.pdf_path and a.csv_path != b.csv_path
        assert len(pdf_files(media)) == 4   # 2 reports x (PDF + CSV)

    def test_write_never_clobbers(self, media):
        dest = media / "r.pdf"
        dest.write_bytes(b"original")
        with pytest.raises(FileExistsError):
            gen._write_atomic(dest, b"new")
        assert dest.read_bytes() == b"original"
        assert [p.name for p in media.iterdir()] == ["r.pdf"]  # no temp left

    def test_reports_are_immutable(self, surveyed):
        r = generate_report(surveyed)
        r.row_count = 999
        with pytest.raises(ValueError, match="immutable"):
            r.save()
        assert Report.objects.get(pk=r.pk).row_count == 3


class TestStoredCsv:
    def test_csv_beside_pdf_is_the_embedded_bytes(self, surveyed, media):
        r = generate_report(surveyed)
        stored = (media / r.csv_path).read_bytes()
        _, embedded = attachment(r, media)
        assert stored == embedded
        assert hashlib.sha256(stored).hexdigest() == r.csv_sha256
        assert Path(r.csv_path).stem == Path(r.pdf_path).stem

    def test_csv_write_failure_leaves_nothing(self, surveyed, media, monkeypatch):
        real = gen._write_atomic

        def fail_on_csv(dest, data, suffix=".pdf"):
            if suffix == ".csv":
                raise OSError("disk full")
            return real(dest, data, suffix)
        monkeypatch.setattr(gen, "_write_atomic", fail_on_csv)
        with pytest.raises(OSError):
            generate_report(surveyed)
        assert Report.objects.count() == 0 and pdf_files(media) == []


class TestLogging:
    def test_fonttools_subset_chatter_never_reaches_root(self, surveyed, media, caplog):
        # ~230 INFO lines per report used to reach the console: WeasyPrint's
        # capture_logs sets the fontTools logger to DEBUG while subsetting.
        import logging
        caplog.set_level(logging.DEBUG)
        generate_report(surveyed)
        leaked = [r for r in caplog.records if r.name.startswith("fontTools")]
        assert leaked == [], f"{len(leaked)} fontTools records reached root"


class TestAllOrNothing:
    def test_pdf_failure_leaves_nothing(self, surveyed, media, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("render failed")
        monkeypatch.setattr(gen, "render_pdf", boom)
        with pytest.raises(RuntimeError):
            generate_report(surveyed)
        assert Report.objects.count() == 0 and pdf_files(media) == []

    def test_row_failure_removes_the_file(self, surveyed, media, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("db failed")
        monkeypatch.setattr(Report.objects, "create", boom)
        with pytest.raises(RuntimeError):
            generate_report(surveyed)
        assert Report.objects.count() == 0 and pdf_files(media) == []


class TestMarsabit:
    def test_modelled_site_report(self, media):
        call_command("seed_marsabit", "--site", "forole", "--scale", "0.05",
                     "--seed", "42", verbosity=0)
        m = Mission.objects.get(metadata__site_code="forole")
        r = generate_report(m)
        assert r.weakest_source == "modelled"
        assert r.row_count == SensorLog.objects.filter(mission=m).count()
        cpm = [b for b in r.summary["quantities"] if b["quantity"] == "cpm"]
        assert len(cpm) == 1 and "omitted" in cpm[0]
        dose = [b for b in r.summary["quantities"] if b["quantity"] == "dose_rate_usvh"]
        values = list(RadiationLog.objects.filter(sensor_log__mission=m)
                      .values_list("dose_rate_usvh", flat=True))
        assert dose[0]["stats"]["max"] == max(values)
        assert dose[0]["stats"]["n"] == len(values)


class TestCommand:
    def test_happy(self, surveyed, media):
        out = io.StringIO()
        call_command("generate_report", "--mission", str(surveyed.pk), stdout=out)
        r = Report.objects.get()
        assert "PASS report generated" in out.getvalue()
        assert r.pdf_sha256 in out.getvalue() and r.csv_sha256 in out.getvalue()

    def test_refusal_is_a_command_error(self, mission):
        with pytest.raises(CommandError, match="COMPLETED"):
            call_command("generate_report", "--mission", str(mission.pk))

    def test_unknown_mission(self, db):
        with pytest.raises(CommandError, match="No mission"):
            call_command("generate_report", "--mission", "999999")
# ─── RANGER V3 END: 16-report-generate ───
