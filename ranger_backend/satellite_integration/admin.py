# ─── RANGER V3 START: satellite integration admin ───
"""Admin for the satellite catalog, queries, and retrieved scenes.

Read-mostly by design: datasets come from `seed_datasets`, queries and images
from `fetch_scenes`. Admin is for inspecting what the pipeline produced, not
for hand-creating rows — hence the wide readonly_fields and the absence of
add permissions on SatelliteImage.
"""
from django.contrib import admin

from .models import SatelliteDataset, SatelliteImage, SatelliteQuery


@admin.register(SatelliteDataset)
class SatelliteDatasetAdmin(admin.ModelAdmin):
    list_display = (
        "name", "code", "provider", "resolution_m", "scale",
        "archive_start", "is_verified", "is_active",
    )
    list_filter = ("provider", "scale", "is_verified", "is_active")
    search_fields = ("name", "code", "gee_collection_id")
    readonly_fields = ("created_at", "updated_at")


class SatelliteImageInline(admin.TabularInline):
    model = SatelliteImage
    extra = 0
    can_delete = False
    fields = ("gee_asset_id", "acquisition_date", "cloud_cover_pct", "has_cog")
    readonly_fields = fields

    @admin.display(boolean=True, description="COG")
    def has_cog(self, obj) -> bool:
        return obj.has_cog

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(SatelliteQuery)
class SatelliteQueryAdmin(admin.ModelAdmin):
    list_display = (
        "__str__", "organization", "dataset", "status",
        "scene_count", "created_at",
    )
    list_filter = ("status", "dataset", "organization")
    search_fields = ("label", "error_message")
    readonly_fields = ("created_at", "updated_at", "completed_at", "scene_count")
    list_select_related = ("organization", "dataset")
    inlines = [SatelliteImageInline]


@admin.register(SatelliteImage)
class SatelliteImageAdmin(admin.ModelAdmin):
    list_display = (
        "gee_asset_id", "dataset", "acquisition_date",
        "cloud_cover_pct", "has_cog", "tiles_stale",
    )
    list_filter = ("dataset", "acquisition_date")
    search_fields = ("gee_asset_id", "cog_path")
    readonly_fields = ("created_at", "downloaded_at", "size_bytes", "properties")
    list_select_related = ("dataset", "query")
    date_hierarchy = "acquisition_date"

    @admin.display(boolean=True, description="COG on disk")
    def has_cog(self, obj) -> bool:
        return obj.has_cog

    @admin.display(boolean=True, description="Tiles stale")
    def tiles_stale(self, obj) -> bool:
        # Surfaced in the list because an expired tile URL is invisible until
        # a map silently renders nothing.
        return obj.tiles_are_stale()

    def has_add_permission(self, request, obj=None) -> bool:
        return False
# ─── RANGER V3 END: satellite integration admin ───
