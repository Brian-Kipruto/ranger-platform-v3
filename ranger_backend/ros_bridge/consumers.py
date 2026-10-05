# ─── RANGER V3 START: 09-live-console ───
"""
DashboardConsumer: read-only, org-scoped live feed.

Auth: the browser cannot set headers on a WebSocket, so the access token rides
in Sec-WebSocket-Protocol, never the URL (URLs land in access logs):

    new WebSocket(url, ["ranger.v1", "jwt.<access token>"])

The server echoes "ranger.v1". Auth happens at connect only; a connection
outlives its 15-min token, and a reconnect must present a fresh one.

Close codes (sent AFTER accept, so the browser actually sees them; a
pre-accept close surfaces as a bare 1006):
    4401  missing / malformed / expired / unknown-user token
    4403  valid user, no organization
"""
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import AccessToken

from .broadcast import dashboard_group

SUBPROTOCOL = "ranger.v1"
TOKEN_PREFIX = "jwt."

CLOSE_UNAUTHENTICATED = 4401
CLOSE_NO_ORG = 4403

_NO_USER = object()


def _token_from_subprotocols(subprotocols) -> str | None:
    for p in subprotocols or ():
        if p.startswith(TOKEN_PREFIX) and len(p) > len(TOKEN_PREFIX):
            return p[len(TOKEN_PREFIX):]
    return None


@database_sync_to_async
def _org_id_for_token(raw: str):
    """Return the user's org id, None for a user with no org, or _NO_USER."""
    try:
        token = AccessToken(raw)  # verifies signature, type and expiry
        user_id = token[api_settings.USER_ID_CLAIM]
    except (TokenError, KeyError):
        return _NO_USER
    row = (
        get_user_model().objects
        .filter(pk=user_id, is_active=True)
        .values("organization_id")
        .first()
    )
    return _NO_USER if row is None else row["organization_id"]


class DashboardConsumer(AsyncJsonWebsocketConsumer):
    group = None

    async def connect(self):
        offered = self.scope.get("subprotocols") or []
        raw = _token_from_subprotocols(offered)
        org_id = _NO_USER if raw is None else await _org_id_for_token(raw)

        # Join BEFORE accept: once the client sees the handshake complete,
        # it is already in its group, so no broadcast can slip past it.
        if org_id is not _NO_USER and org_id is not None:
            self.group = dashboard_group(org_id)
            await self.channel_layer.group_add(self.group, self.channel_name)

        await self.accept(subprotocol=SUBPROTOCOL if SUBPROTOCOL in offered else None)

        if org_id is _NO_USER:
            await self.close(code=CLOSE_UNAUTHENTICATED)
        elif org_id is None:
            await self.close(code=CLOSE_NO_ORG)

    async def disconnect(self, code):
        if self.group:
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        pass  # read-only feed: client messages are ignored

    async def sensorlog_message(self, event):
        await self.send_json(event["payload"])
# ─── RANGER V3 END: 09-live-console ───
