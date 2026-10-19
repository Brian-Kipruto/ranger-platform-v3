# ─── RANGER V3 START: 14-teleop ───
"""TeleopConsumer: the console's authenticated drive socket (F14 5a, fork 1).

    new WebSocket("/ws/teleop/RANGER-PRIME-001/", ["ranger.v1", "jwt.<access token>"])

Same token transport as the live console (ADR-0016): Sec-WebSocket-Protocol, never
the URL, checked once at connect. Then, in order:
    4401  missing / malformed / expired / unknown-user token
    4403  valid user, no organization
    4404  no robot with that id in the user's organization (unknown and someone else's
          robot look the same: existence is not leaked)
    4405  user lacks core.drive_robot (grant via the Drivers group: grant_drive)
    4409  another session is driving this robot, or this session lost its lease
All closes come AFTER accept, so the browser sees the code (a pre-accept close is a
bare 1006).

Client -> server (JSON):
    {"type": "drive", "lin": <-1..1>, "ang": <-1..1>}   normalised, +ang turns left
    {"type": "hold"}                                    keepalive while idle (< TTL)
    {"type": "stop"}                                    explicit zero command
Server -> client:
    {"type": "ready", "robot": "<robot_id_str>"}
    {"type": "error", "reason": "bad_message" | "value" | "rate" | "relay_offline"}

Commands go to teleop_relay over the channel layer (teleop.py), stamped with the
server's time. This consumer never repeats a command: the browser's deadman decides
what is sent, and silence stops the robot (uno_bridge, 250 ms). Disconnect sends one
zero command and releases the lease.
"""
import time

from channels.db import database_sync_to_async
from channels.exceptions import ChannelFull
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import AccessToken

from core.models import Robot

from .consumers import CLOSE_NO_ORG, CLOSE_UNAUTHENTICATED, SUBPROTOCOL, _token_from_subprotocols
from .drive_lock import get_drive_lock
from .teleop import make_cmd, teleop_channel

CLOSE_NO_ROBOT = 4404
CLOSE_NOT_DRIVER = 4405
CLOSE_ROBOT_BUSY = 4409

DRIVE_PERM = "core.drive_robot"
MAX_MSGS_PER_S = 30   # the console sends 20 Hz; anything faster is dropped


@database_sync_to_async
def _authorise(raw, robot_id_str):
    """(close_code, None) or (None, robot_pk)."""
    if raw is None:
        return CLOSE_UNAUTHENTICATED, None
    try:
        user_id = AccessToken(raw)[api_settings.USER_ID_CLAIM]
    except (TokenError, KeyError):
        return CLOSE_UNAUTHENTICATED, None
    user = get_user_model().objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        return CLOSE_UNAUTHENTICATED, None
    if user.organization_id is None:
        return CLOSE_NO_ORG, None
    robot_pk = (Robot.objects
                .filter(robot_id_str=robot_id_str, organization_id=user.organization_id)
                .values_list("pk", flat=True).first())
    if robot_pk is None:
        return CLOSE_NO_ROBOT, None
    if not user.has_perm(DRIVE_PERM):
        return CLOSE_NOT_DRIVER, None
    return None, robot_pk


class TeleopConsumer(AsyncJsonWebsocketConsumer):
    robot_pk = None
    lock = None
    driving = False

    async def connect(self):
        offered = self.scope.get("subprotocols") or []
        robot_id = self.scope["url_route"]["kwargs"]["robot_id"]
        code, robot_pk = await _authorise(_token_from_subprotocols(offered), robot_id)
        if code is None:
            self.lock = get_drive_lock()
            if await self.lock.acquire(robot_pk, self.channel_name):
                self.robot_pk, self.driving = robot_pk, True
            else:
                code = CLOSE_ROBOT_BUSY

        await self.accept(subprotocol=SUBPROTOCOL if SUBPROTOCOL in offered else None)
        if code is not None:
            await self.close(code=code)
            return
        self.window_start, self.window_count = time.monotonic(), 0
        await self.send_json({"type": "ready", "robot": robot_id})

    async def disconnect(self, code):
        if self.driving:
            self.driving = False
            await self._forward(0.0, 0.0, report=False)
            await self.lock.release(self.robot_pk, self.channel_name)
        if self.lock is not None:
            await self.lock.close()

    async def receive_json(self, content, **kwargs):
        if not self.driving:
            return
        if not self._within_rate():
            await self.send_json({"type": "error", "reason": "rate"})
            return
        kind = content.get("type") if isinstance(content, dict) else None
        if kind not in ("drive", "hold", "stop"):
            await self.send_json({"type": "error", "reason": "bad_message"})
            return
        if not await self.lock.refresh(self.robot_pk, self.channel_name):
            # Lease lapsed and someone else took the robot: this session must not drive.
            self.driving = False
            await self.close(code=CLOSE_ROBOT_BUSY)
            return
        if kind == "hold":
            return
        if kind == "stop":
            await self._forward(0.0, 0.0)
            return
        try:
            make_cmd(content.get("lin"), content.get("ang"), 0.0)
        except ValueError:
            await self.send_json({"type": "error", "reason": "value"})
            return
        await self._forward(content["lin"], content["ang"])

    def _within_rate(self):
        now = time.monotonic()
        if now - self.window_start >= 1.0:
            self.window_start, self.window_count = now, 0
        self.window_count += 1
        return self.window_count <= MAX_MSGS_PER_S

    async def _forward(self, lin, ang, report=True):
        try:
            await self.channel_layer.send(
                teleop_channel(self.robot_pk), make_cmd(lin, ang, time.time()))
        except ChannelFull:
            # Nobody is draining the channel: teleop_relay is not running.
            if report:
                await self.send_json({"type": "error", "reason": "relay_offline"})
# ─── RANGER V3 END: 14-teleop ───
