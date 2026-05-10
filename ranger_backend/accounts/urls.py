# ─── RANGER V3 START: auth urls ───
"""URL routes for the accounts app — auth endpoints + user self-service."""
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    # /api/users/me/ — current user profile
    path("users/me/", views.UserMeView.as_view(), name="user-me"),
    # /api/auth/token/ — login, returns {access, user} + sets refresh cookie
    path("auth/token/", views.CustomTokenObtainPairView.as_view(), name="token-obtain"),
    # ─── RANGER V3 START: auth ───
    # /api/auth/token/refresh/ — reads refresh cookie, returns new access, rotates cookie
    path("auth/token/refresh/", views.CookieTokenRefreshView.as_view(), name="token-refresh"),
    # /api/auth/logout/ — blacklists refresh, clears cookie
    path("auth/logout/", views.LogoutView.as_view(), name="logout"),
    # ─── RANGER V3 END: auth ───
]
# ─── RANGER V3 END: auth urls ───