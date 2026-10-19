# ─── RANGER V3 START: 09-live-console ───
from django.urls import re_path

from .consumers import DashboardConsumer
from .teleop_consumer import TeleopConsumer  # 14-teleop

websocket_urlpatterns = [
    re_path(r"^ws/dashboard/$", DashboardConsumer.as_asgi()),
    # ─── RANGER V3 START: 14-teleop ───
    re_path(r"^ws/teleop/(?P<robot_id>[A-Za-z0-9_\-]{1,100})/$", TeleopConsumer.as_asgi()),
    # ─── RANGER V3 END: 14-teleop ───
]
# ─── RANGER V3 END: 09-live-console ───
