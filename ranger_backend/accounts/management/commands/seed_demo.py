# ─── RANGER V3 START: seed_demo ───
"""
seed_demo — create demo organizations, groups, and users for the Field
Console role-demo login buttons (Feature 06).

This exists so the login page's three role-demo buttons log in for REAL,
against actual accounts, rather than faking a session. It is a development
convenience: idempotent (safe to re-run), creates nothing if everything
already exists, and never modifies pre-existing users (so it will not touch
your real superuser account).

What it creates:
  * Groups:  Operator, Client, Community  (permission buckets; perms attached
             later when ADR 0007 authorization work lands — empty for now)
  * Orgs:    ByteAnza      (slug 'byteanza',     theme_color #0ea5e9 teal)
             Magadi Soda Co (slug 'magadi-soda', theme_color #f5a623 amber)
             — two DIFFERENT theme_colors so the accent-follows-org wiring is
               visibly provable: logging in as each demo user repaints --accent.
  * Users:   operator@byteanza.com   → ByteAnza,  Operator group, SUPERUSER
             client@magadi.com       → Magadi,    Client group
             community@public.com    → no org,    Community group

All three share one dev password, printed on completion. These credentials
are dev-only and also live in the frontend at src/config/demoAccounts.ts.

Tenancy note: ByteAnza must exist for run_simulation's default seed-robot path
(it looks up Organization slug 'byteanza'). This command guarantees it.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Organization

User = get_user_model()

# Shared dev password for all demo accounts. Dev-only; mirrored in the
# frontend demoAccounts config. Not a secret — these are throwaway demo logins.
DEMO_PASSWORD = "RangerDemo1234!"

# Groups that represent the three Field Console roles. Permissions are NOT
# attached here — that's the ADR 0007 authorization-debt thread. For now they
# exist so users have a role bucket and the nav/role concept has real backing.
DEMO_GROUPS = ("Operator", "Client", "Community")

# (slug, name, theme_color) — two visibly different accents to prove the
# org-driven --accent token end to end.
DEMO_ORGS = (
    ("byteanza", "ByteAnza", "#0ea5e9"),
    ("magadi-soda", "Magadi Soda Co.", "#f5a623"),
)

# (username, email, org_slug_or_None, group_name, is_superuser)
# Username == email deliberately: the Field Console login shows the email in
# the "Operator ID" field, and simplejwt authenticates on `username`. Making
# them identical means the thing displayed is the thing you log in with.
DEMO_USERS = (
    ("operator@byteanza.com", "operator@byteanza.com", "byteanza", "Operator", True),
    ("client@magadi.com", "client@magadi.com", "magadi-soda", "Client", False),
    ("community@public.com", "community@public.com", None, "Community", False),
)


class Command(BaseCommand):
    help = (
        "Create demo organizations, groups, and users for the Field Console "
        "role-demo login buttons. Idempotent; never modifies existing users."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default=DEMO_PASSWORD,
            help=f"Password for all demo users (default: {DEMO_PASSWORD}).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        password = options["password"]

        groups = self._ensure_groups()
        orgs = self._ensure_orgs()
        self._ensure_users(groups, orgs, password)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("seed_demo complete. Demo logins:"))
        for username, email, org_slug, group_name, is_super in DEMO_USERS:
            tag = " [superuser]" if is_super else ""
            org_label = org_slug or "—"
            self.stdout.write(
                f"  {username:<24} / {password}   "
                f"({group_name}, org={org_label}){tag}"
            )

    # ─── groups ──────────────────────────────────────────────────────
    def _ensure_groups(self) -> dict[str, Group]:
        groups: dict[str, Group] = {}
        for name in DEMO_GROUPS:
            group, created = Group.objects.get_or_create(name=name)
            groups[name] = group
            verb = "Created" if created else "Exists"
            self.stdout.write(f"{verb} group: {name}")
        return groups

    # ─── orgs ────────────────────────────────────────────────────────
    def _ensure_orgs(self) -> dict[str, Organization]:
        orgs: dict[str, Organization] = {}
        for slug, name, theme_color in DEMO_ORGS:
            org, created = Organization.objects.get_or_create(
                slug=slug,
                defaults={"name": name, "theme_color": theme_color},
            )
            orgs[slug] = org
            verb = "Created" if created else "Exists"
            self.stdout.write(
                f"{verb} org: {name} ({slug}, {org.theme_color})"
            )
        return orgs

    # ─── users ───────────────────────────────────────────────────────
    def _ensure_users(
        self,
        groups: dict[str, Group],
        orgs: dict[str, Organization],
        password: str,
    ) -> None:
        for username, email, org_slug, group_name, is_super in DEMO_USERS:
            if User.objects.filter(username=username).exists():
                # Never modify an existing account — could be the real
                # superuser or a user the operator created by hand.
                self.stdout.write(f"Exists user: {username} (left untouched)")
                continue

            org = orgs.get(org_slug) if org_slug else None
            if is_super:
                user = User.objects.create_superuser(
                    username=username,
                    email=email,
                    password=password,
                )
                # create_superuser doesn't take organization; set it after.
                if org is not None:
                    user.organization = org
                    user.save(update_fields=["organization"])
            else:
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    organization=org,
                )
            user.groups.add(groups[group_name])
            self.stdout.write(
                self.style.SUCCESS(f"Created user: {username} ({group_name})")
            )
# ─── RANGER V3 END: seed_demo ───