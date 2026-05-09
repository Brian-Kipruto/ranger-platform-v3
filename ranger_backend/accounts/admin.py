"""
─── RANGER V3 START: accounts admin ───
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "email", "organization", "is_staff", "is_active")
    list_filter = ("organization", "is_staff", "is_active", "groups")
    search_fields = ("username", "email", "first_name", "last_name")

    fieldsets = UserAdmin.fieldsets + (
        ("R.A.N.G.E.R.", {"fields": ("organization", "phone", "mfa_enabled")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("R.A.N.G.E.R.", {"fields": ("organization", "phone")}),
    )

# ─── RANGER V3 END: accounts admin ───