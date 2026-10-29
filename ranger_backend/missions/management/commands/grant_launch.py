# ─── RANGER V3 START: 15-mission-advance ───
"""Give (or take away) mission start: the Mission Operators group carries
missions.launch_mission. Same shape as ros_bridge grant_drive.

    python manage.py grant_launch operator@byteanza.com
    python manage.py grant_launch operator@byteanza.com --revoke

Idempotent. Superusers can launch regardless (has_perm).
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

OPERATORS_GROUP = "Mission Operators"


def operators_group() -> Group:
    group, _ = Group.objects.get_or_create(name=OPERATORS_GROUP)
    perm = Permission.objects.get(content_type__app_label="missions", codename="launch_mission")
    group.permissions.add(perm)
    return group


class Command(BaseCommand):
    help = "Add a user to (or remove them from) the Mission Operators group (missions.launch_mission)."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--revoke", action="store_true")

    @transaction.atomic
    def handle(self, *args, **opts):
        user = get_user_model().objects.filter(username=opts["username"]).first()
        if user is None:
            raise CommandError(f"No user {opts['username']!r}")
        group = operators_group()
        if opts["revoke"]:
            user.groups.remove(group)
        else:
            user.groups.add(group)
        user = get_user_model().objects.get(pk=user.pk)  # drop the cached permission set
        can = user.has_perm("missions.launch_mission")
        note = " (superuser: can always launch)" if user.is_superuser else ""
        self.stdout.write(f"{user.username}: launch_mission={can}{note}")
# ─── RANGER V3 END: 15-mission-advance ───
