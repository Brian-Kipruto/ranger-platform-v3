# ─── RANGER V3 START: 16-report-download ───
"""Give (or take away) report generation: the Report Authors group carries
reports.generate_report. Same shape as missions grant_launch.

    python manage.py grant_reports operator@knra.go.ke
    python manage.py grant_reports operator@knra.go.ke --revoke

Idempotent. Superusers can generate regardless (has_perm). Listing and
downloading need only membership of the report's organization.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

AUTHORS_GROUP = "Report Authors"


def authors_group() -> Group:
    group, _ = Group.objects.get_or_create(name=AUTHORS_GROUP)
    perm = Permission.objects.get(content_type__app_label="reports", codename="generate_report")
    group.permissions.add(perm)
    return group


class Command(BaseCommand):
    help = "Add a user to (or remove them from) the Report Authors group (reports.generate_report)."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--revoke", action="store_true")

    @transaction.atomic
    def handle(self, *args, **opts):
        user = get_user_model().objects.filter(username=opts["username"]).first()
        if user is None:
            raise CommandError(f"No user {opts['username']!r}")
        group = authors_group()
        if opts["revoke"]:
            user.groups.remove(group)
            self.stdout.write(self.style.SUCCESS(f"PASS {user.username} removed from {AUTHORS_GROUP}"))
        else:
            user.groups.add(group)
            self.stdout.write(self.style.SUCCESS(f"PASS {user.username} in {AUTHORS_GROUP}"))
# ─── RANGER V3 END: 16-report-download ───
