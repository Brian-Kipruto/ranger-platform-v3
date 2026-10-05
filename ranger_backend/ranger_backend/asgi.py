"""
─── RANGER V3 START: ASGI config ───
Routes HTTP and WebSocket traffic.
"""
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ranger_backend.settings.development")

# Initialize Django ASGI app early so apps are ready before importing channels routing
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

# ─── RANGER V3 START: 09-live-console ───
from ros_bridge.routing import websocket_urlpatterns  # noqa: E402
# ─── RANGER V3 END: 09-live-console ───

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        URLRouter(websocket_urlpatterns)
    ),
})

# ─── RANGER V3 END: ASGI config ───