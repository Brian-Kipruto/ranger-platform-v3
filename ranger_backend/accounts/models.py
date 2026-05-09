"""
─── RANGER V3 START: accounts models ───
Multi-tenant foundation: Organization (tenant) and CustomUser (org-scoped).
Permissions are managed via Django Groups, not a `role` field.
"""
from django.contrib.auth.models import AbstractUser
from django.db import models


class Organization(models.Model):
    """A tenant. Every robot, mission, sensor log, etc. belongs to an Organization."""

    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=200, unique=True, db_index=True)

    # Branding (per-tenant logo and accent color)
    logo = models.ImageField(upload_to="org_logos/", null=True, blank=True)
    theme_color = models.CharField(
        max_length=7,
        default="#0ea5e9",
        help_text="Hex color, e.g. #0ea5e9",
    )

    # Status
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        permissions = (
            ("change_branding", "Can change organization branding"),
        )

    def __str__(self) -> str:
        return self.name


class CustomUser(AbstractUser):
    """User scoped to an Organization. Permissions via Django Groups."""

    # Nullable because superusers (ByteAnza staff) may not belong to a single org
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="users",
        null=True,
        blank=True,
    )

    # Phone number for SMS alerts (future)
    phone = models.CharField(max_length=20, blank=True, default="")

    # MFA flag (TOTP setup deferred to a later phase)
    mfa_enabled = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["username"]

    def __str__(self) -> str:
        if self.organization:
            return f"{self.username} ({self.organization.name})"
        return self.username

# ─── RANGER V3 END: accounts models ───