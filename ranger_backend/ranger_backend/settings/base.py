"""
─── RANGER V3 START: base settings ───
Settings shared across all environments.
Override per-environment in development.py / production.py.
"""
import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

# Project paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # points to ranger_backend/
PROJECT_ROOT = BASE_DIR.parent  # points to ranger-platform-v3/

# Load .env from project root
load_dotenv(PROJECT_ROOT / ".env")


def env(key: str, default=None, required: bool = False) -> str:
    value = os.getenv(key, default)
    if required and value is None:
        raise RuntimeError(f"Missing required env var: {key}")
    return value


# ─── Core ───
SECRET_KEY = env("DJANGO_SECRET_KEY", required=True)
DEBUG = False  # Overridden in development.py
ALLOWED_HOSTS: list[str] = []

# ─── Applications ───
DJANGO_APPS = [
    "daphne",  # Must come BEFORE django.contrib.staticfiles to override runserver
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # ─── RANGER V3 START: geospatial ───
    "django.contrib.gis",  # F10.1: GeoDjango — PostGIS backend + geometry fields
    # ─── RANGER V3 END: geospatial ───
]


THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    # ─── RANGER V3 START: auth ───
    "rest_framework_simplejwt.token_blacklist",
    # ─── RANGER V3 END: auth ───
    "channels",
    "corsheaders",
]

LOCAL_APPS = [
    "accounts",
    "core",
    "missions",
    "ros_bridge",
    "visualization",
    "alerts",
    "reports",
    "billing",
    "platform_config",
    "ai_assistant",
    "community",
    "fleet",
    "audit",
    "satellite_integration",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "ranger_backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "ranger_backend.wsgi.application"
ASGI_APPLICATION = "ranger_backend.asgi.application"

# ─── Database ───
DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": env("POSTGRES_DB", required=True),
        "USER": env("POSTGRES_USER", required=True),
        "PASSWORD": env("POSTGRES_PASSWORD", required=True),
        "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env("POSTGRES_PORT", "5432"),
    }
}

# ─── Custom User Model ───
# CRITICAL: Set BEFORE first migration. Never change after data exists.
AUTH_USER_MODEL = "accounts.CustomUser"

# ─── Channels ───
REDIS_HOST = env("REDIS_HOST", "localhost")
REDIS_PORT = int(env("REDIS_PORT", "6379"))

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [(REDIS_HOST, REDIS_PORT)],
        },
    },
}

# ─── DRF ───
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}

# ─── JWT ───
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    # ─── RANGER V3 START: auth ───
    # Blacklist old refresh tokens after rotation so leaked tokens die fast.
    # Requires rest_framework_simplejwt.token_blacklist in INSTALLED_APPS.
    "BLACKLIST_AFTER_ROTATION": True,
    # ─── RANGER V3 END: auth ───
    "SIGNING_KEY": env("JWT_SIGNING_KEY", required=True),
    "ALGORITHM": "HS256",
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# ─── RANGER V3 START: auth ───
# Refresh token cookie config. The refresh token lives in an httpOnly
# cookie so JS (and therefore XSS) can't read it. Access token still goes
# in the response body and lives in memory + localStorage on the frontend.
#
# Path is restricted to /api/auth/ so the browser only sends it on
# refresh/logout, minimizing exposure on every other API call.
#
# Secure is False in DEBUG so dev works over HTTP. Flip DEBUG to False
# in production and the cookie auto-upgrades to HTTPS-only.
REFRESH_COOKIE = {
    "name": "ranger_refresh",
    "path": "/api/auth/",
    "httponly": True,
    "samesite": "Strict",
    # 'secure' is computed at request time in views (reads settings.DEBUG)
    # because base.py is evaluated before development.py overrides DEBUG.
    # max_age in seconds. Matches REFRESH_TOKEN_LIFETIME above.
    "max_age": int(SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
}
# ─── RANGER V3 END: auth ───

# ─── Password validation ───
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ─── Internationalization ───
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True

# ─── Static / Media ───
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ─── RANGER V3 END: base settings ───
