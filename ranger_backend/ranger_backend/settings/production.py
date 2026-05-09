"""
─── RANGER V3 START: production settings ───
Hardened settings for production deployment.
TODO: completed in deployment phase.
"""
from .base import *  # noqa
from .base import env

DEBUG = False
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS", "").split(",")

# Security headers
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ─── RANGER V3 END: production settings ───
