# ─── RANGER V3 START: 16-report-generate ───
"""manage.py generate_report --mission <pk> [--user <username>]

Generates one compliance report and prints where it went and its hashes, so
it can be checked with sha256sum and a psql query before any UI exists.
"""
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from missions.models import Mission
from reports.generate import ReportError, generate_report


class Command(BaseCommand):
    help = "Generate a compliance report PDF for one COMPLETED mission."

    def add_arguments(self, parser):
        parser.add_argument("--mission", type=int, required=True)
        parser.add_argument("--user", type=str, default=None,
                            help="Username recorded as generated_by.")

    def handle(self, *args, **opts):
        try:
            mission = Mission.objects.select_related(
                "organization", "robot"
            ).get(pk=opts["mission"])
        except Mission.DoesNotExist:
            raise CommandError(f"No mission with pk {opts['mission']}.")

        user = None
        if opts["user"]:
            try:
                user = get_user_model().objects.get(username=opts["user"])
            except get_user_model().DoesNotExist:
                raise CommandError(f"No user {opts['user']!r}.")

        try:
            report = generate_report(mission, user=user)
        except ReportError as e:
            raise CommandError(str(e))

        path = Path(settings.MEDIA_ROOT) / report.pdf_path
        self.stdout.write(f"report     {report.pk}")
        self.stdout.write(f"mission    {mission.pk} {mission.name}")
        self.stdout.write(f"rows       {report.row_count}")
        self.stdout.write(f"weakest    {report.weakest_source}")
        self.stdout.write(f"pdf        {path}")
        self.stdout.write(f"pdf_sha256 {report.pdf_sha256}")
        self.stdout.write(f"csv_sha256 {report.csv_sha256}")
        self.stdout.write(self.style.SUCCESS("PASS report generated"))
# ─── RANGER V3 END: 16-report-generate ───
