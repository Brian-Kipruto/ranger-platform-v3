# ─── RANGER V3 START: 09-live-console ───
from django.urls import re_path

from .consumers import DashboardConsumer

websocket_urlpatterns = [
    re_path(r"^ws/dashboard/$", DashboardConsumer.as_asgi()),
]
# ─── RANGER V3 END: 09-live-console ───
