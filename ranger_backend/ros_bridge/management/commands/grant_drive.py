# ─── RANGER V3 START: 14-teleop ───
"""Give (or take away) console driving: the Drivers group carries core.drive_robot.

    python manage.py grant_drive operator@byteanza.com
    python manage.py grant_drive operator@byteanza.com --revoke

Idempotent. Superusers can drive regardless (has_perm), so this is for everyone else.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

DRIVERS_GROUP = "Drivers"


def drivers_group() -> Group:
    group, _ = Group.objects.get_or_create(name=DRIVERS_GROUP)
    perm = Permission.objects.get(content_type__app_label="core", codename="drive_robot")
    group.permissions.add(perm)
    return group


class Command(BaseCommand):
    help = "Add a user to (or remove them from) the Drivers group (core.drive_robot)."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--revoke", action="store_true")

    @transaction.atomic
    def handle(self, *args, **opts):
        user = get_user_model().objects.filter(username=opts["username"]).first()
        if user is None:
            raise CommandError(f"No user {opts['username']!r}")
        group = drivers_group()
        if opts["revoke"]:
            user.groups.remove(group)
        else:
            user.groups.add(group)
        user = get_user_model().objects.get(pk=user.pk)  # drop the cached permission set
        can = user.has_perm("core.drive_robot")
        note = " (superuser: can always drive)" if user.is_superuser else ""
        self.stdout.write(f"{user.username}: drive_robot={can}{note}")
# ─── RANGER V3 END: 14-teleop ───
