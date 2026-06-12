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
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# ─── RANGER V3 END: URL routing ───