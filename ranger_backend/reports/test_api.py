# ─── RANGER V3 START: 16-report-download ───
"""Report API (7c): tenancy on list/generate/download, permission on
generate, integrity on download. Every refusal is followed by the owner
succeeding immediately, timed: a guard that also blocks the owner is broken."""
import hashlib
import time
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from core.models import SensorLog
from missions.models import Mission
from reports.management.commands.grant_reports import authors_group
from reports.models import Report

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def client_for(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.fixture
def author(org):
    u = User.objects.create_user(username="author", password="Pw-123456789!", organization=org)
    u.groups.add(authors_group())
    return client_for(u)


@pytest.fixture
def reader(org):
    return client_for(User.objects.create_user(username="reader", password="Pw-123456789!", organization=org))


@pytest.fixture
def outsider(other_org):
    u = User.objects.create_user(username="outsider", password="Pw-123456789!", organization=other_org)
    u.groups.add(authors_group())   # has the permission, wrong tenant
    return client_for(u)


@pytest.fixture
def done(mission, sensor_log_at):
    for i in range(3):
        sensor_log_at(-1.29 - i * 1e-4, 36.82, mission=mission, radiation=100.0 * (i + 1))
    SensorLog.objects.filter(mission=mission).update(source="live")
    mission.status = Mission.Status.COMPLETED
    mission.save(update_fields=["status"])
    return mission


def timed(fn):
    t = time.perf_counter()
    r = fn()
    return r, (time.perf_counter() - t) * 1000


class TestGenerate:
    def test_author_generates(self, author, done, media):
        r = author.post("/api/reports/", {"mission": done.pk}, format="json")
        assert r.status_code == 201, r.data
        assert r.data["mission"] == done.pk and r.data["has_csv"] is True
        assert "pdf_path" not in r.data and "csv_path" not in r.data
        assert Report.objects.get(pk=r.data["id"]).generated_by.username == "author"

    def test_reader_403_then_author_ok(self, reader, author, done, media):
        refused, _ = timed(lambda: reader.post("/api/reports/", {"mission": done.pk}, format="json"))
        assert refused.status_code == 403 and Report.objects.count() == 0
        ok, ms = timed(lambda: author.post("/api/reports/", {"mission": done.pk}, format="json"))
        assert ok.status_code == 201, f"owner blocked after refusal ({ms:.0f} ms)"

    def test_other_org_mission_is_404_then_owner_ok(self, outsider, author, done, media):
        refused, _ = timed(lambda: outsider.post("/api/reports/", {"mission": done.pk}, format="json"))
        assert refused.status_code == 404 and Report.objects.count() == 0
        ok, ms = timed(lambda: author.post("/api/reports/", {"mission": done.pk}, format="json"))
        assert ok.status_code == 201, f"owner blocked after refusal ({ms:.0f} ms)"

    def test_not_completed_is_409(self, author, mission, sensor_log_at, media):
        sensor_log_at(-1.29, 36.82, mission=mission, radiation=10.0)
        r = author.post("/api/reports/", {"mission": mission.pk}, format="json")
        assert r.status_code == 409 and "COMPLETED" in r.data["detail"]

    @pytest.mark.parametrize("body", [{}, {"mission": "x"}, {"mission": None}])
    def test_bad_body_is_400(self, author, body):
        assert author.post("/api/reports/", body, format="json").status_code == 400

    def test_unauthenticated(self, api_client, done):
        assert api_client.post("/api/reports/", {"mission": done.pk}, format="json").status_code == 401


class TestList:
    def test_lists_own_org_only(self, author, outsider, reader, done, media):
        author.post("/api/reports/", {"mission": done.pk}, format="json")
        assert outsider.get("/api/reports/").data["count"] == 0
        r = reader.get("/api/reports/")
        assert r.data["count"] == 1
        row = r.data["results"][0]
        assert row["weakest_source"] == "simulated" and row["registry_version"]
        assert "pdf_path" not in row and "summary" not in row


class TestDownload:
    @pytest.fixture
    def report(self, author, done, media):
        pk = author.post("/api/reports/", {"mission": done.pk}, format="json").data["id"]
        return Report.objects.get(pk=pk)

    @pytest.mark.parametrize("kind", ["pdf", "csv"])
    def test_reader_downloads_exact_bytes(self, reader, report, media, kind):
        r = reader.get(f"/api/reports/{report.pk}/{kind}/")
        assert r.status_code == 200
        body = r.content
        expected = report.pdf_sha256 if kind == "pdf" else report.csv_sha256
        assert hashlib.sha256(body).hexdigest() == expected == r["X-Ranger-Sha256"]
        assert "attachment" in r["Content-Disposition"]
        assert "no-store" in r["Cache-Control"]

    @pytest.mark.parametrize("kind", ["pdf", "csv"])
    def test_other_org_404_then_owner_ok(self, outsider, reader, report, kind):
        refused, _ = timed(lambda: outsider.get(f"/api/reports/{report.pk}/{kind}/"))
        assert refused.status_code == 404
        ok, ms = timed(lambda: reader.get(f"/api/reports/{report.pk}/{kind}/"))
        assert ok.status_code == 200, f"owner blocked after refusal ({ms:.0f} ms)"

    def test_unknown_report_404(self, reader):
        assert reader.get("/api/reports/999999/pdf/").status_code == 404

    @pytest.mark.parametrize("kind,field", [("pdf", "pdf_path"), ("csv", "csv_path")])
    def test_tampered_file_refused_then_restored(self, reader, report, media, kind, field):
        path = media / getattr(report, field)
        original = path.read_bytes()
        path.write_bytes(original + b"tampered")
        refused = reader.get(f"/api/reports/{report.pk}/{kind}/")
        assert refused.status_code == 409 and "Integrity check failed" in refused.data["detail"]
        path.write_bytes(original)
        ok, ms = timed(lambda: reader.get(f"/api/reports/{report.pk}/{kind}/"))
        assert ok.status_code == 200, f"not served after restore ({ms:.0f} ms)"

    def test_missing_file_409(self, reader, report, media):
        (media / report.pdf_path).unlink()
        r = reader.get(f"/api/reports/{report.pk}/pdf/")
        assert r.status_code == 409 and "missing" in r.data["detail"]

    def test_pre_7c_report_has_no_csv(self, reader, report):
        Report.objects.filter(pk=report.pk).update(csv_path="")
        r = reader.get(f"/api/reports/{report.pk}/csv/")
        assert r.status_code == 404 and "predates" in r.data["detail"]

    def test_path_outside_reports_root_refused(self, reader, report, media):
        # A byte-identical copy OUTSIDE reports/: its hash matches, so only
        # the path guard can refuse it. (A non-matching file would be refused
        # by the integrity check and prove nothing about the guard.)
        outside = media / "outside.pdf"
        outside.write_bytes((media / report.pdf_path).read_bytes())
        Report.objects.filter(pk=report.pk).update(pdf_path="reports/../outside.pdf")
        r = reader.get(f"/api/reports/{report.pk}/pdf/")
        assert r.status_code == 409 and "path is invalid" in r.data["detail"]
        assert Path(outside).exists()


class TestGrantCommand:
    def test_grant_and_revoke(self, org):
        from django.core.management import call_command
        u = User.objects.create_user(username="g", password="Pw-123456789!", organization=org)
        call_command("grant_reports", "g", stdout=open("/dev/null", "w"))
        assert User.objects.get(pk=u.pk).has_perm("reports.generate_report")
        call_command("grant_reports", "g", "--revoke", stdout=open("/dev/null", "w"))
        assert not User.objects.get(pk=u.pk).has_perm("reports.generate_report")
# ─── RANGER V3 END: 16-report-download ───
