"""
─── RANGER V3 START: URL routing ───
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    # API routes will be added per-app as features are built
    path("api/", include("accounts.urls")),
    # ─── RANGER V3 START: data explorer ───
    path("api/", include("core.urls")),
    # ─── RANGER V3 END: data explorer ───
    # ─── RANGER V3 START: satellite EO (F10.2) ───
    # Included WITH the prefix, unlike core.urls: the satellite surface is a
    # namespace rather than four sibling endpoints, and F10.3's render route
    # lands under the same prefix.
    path("api/satellite/", include("satellite_integration.urls")),
    # ─── RANGER V3 END: satellite EO (F10.2) ───
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# ─── RANGER V3 END: URL routing ───