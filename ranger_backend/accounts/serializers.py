# ─── RANGER V3 START: auth serializers ───
"""
Serializers for the auth feature.

UserMeSerializer is the canonical "who am I" payload returned by
/api/users/me/ and embedded in the login response. The frontend depends
on this exact shape — change with care.
"""
from django.contrib.auth.models import Group
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import CustomUser, Organization


class OrganizationNestedSerializer(serializers.ModelSerializer):
    """Org info nested inside the user payload. Read-only."""

    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = ("id", "name", "slug", "theme_color", "logo_url")
        read_only_fields = fields

    def get_logo_url(self, obj: Organization) -> str | None:
        if not obj.logo:
            return None
        request = self.context.get("request")
        url = obj.logo.url
        # If we have a request, return an absolute URL so the frontend
        # doesn't have to know the backend host. Falls back to relative
        # if context is missing (e.g. called outside a view).
        return request.build_absolute_uri(url) if request else url


class GroupNestedSerializer(serializers.ModelSerializer):
    """Lean group info — just id + name. The full permissions list is
    flattened on the user object instead, so the frontend doesn't have to
    walk groups to do permission checks."""

    class Meta:
        model = Group
        fields = ("id", "name")
        read_only_fields = fields


class UserMeSerializer(serializers.ModelSerializer):
    """
    The canonical user payload.

    Permissions are returned as a flat list of "app_label.codename" strings
    (e.g. "missions.launch_mission"). This matches Django's user.has_perm()
    format and lets the frontend do simple `permissions.includes(code)` checks.
    """

    organization = OrganizationNestedSerializer(read_only=True)
    groups = GroupNestedSerializer(many=True, read_only=True)
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = (
            "id",
            "username",
            "email",
            "organization",
            "groups",
            "permissions",
            "is_superuser",
            "is_staff",
            "mfa_enabled",
            "phone",
        )
        read_only_fields = fields

    def get_permissions(self, obj: CustomUser) -> list[str]:
        # get_all_permissions() returns the union of user perms and group perms
        # in "app_label.codename" format. Superusers implicitly have all perms,
        # but we still return the explicit list for non-superusers and let the
        # frontend short-circuit on is_superuser.
        if obj.is_superuser:
            # For superusers, return [] and rely on is_superuser flag.
            # Returning every permission in the system would be a huge payload
            # and the frontend's hasPermission() helper checks is_superuser first.
            return []
        return sorted(obj.get_all_permissions())


from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Extends simplejwt's default login serializer to embed the full user
    payload in the response. Saves a round-trip on login: the frontend
    gets {access, user} + the refresh cookie in one call instead of having
    to call /api/users/me/ separately right after login.

    Note: this serializer still produces {access, refresh, user}. The view
    (CustomTokenObtainPairView) is responsible for moving 'refresh' from
    the body into the Set-Cookie header before returning the response.
    """

    def validate(self, attrs: dict) -> dict:
        # Parent class authenticates and produces {"access": "...", "refresh": "..."}
        data = super().validate(attrs)
        # self.user is set by the parent during authentication.
        # Pass request context so OrganizationNestedSerializer can build
        # an absolute logo_url.
        user_data = UserMeSerializer(
            self.user,
            context={"request": self.context.get("request")},
        ).data
        data["user"] = user_data
        return data
# ─── RANGER V3 END: auth serializers ───

