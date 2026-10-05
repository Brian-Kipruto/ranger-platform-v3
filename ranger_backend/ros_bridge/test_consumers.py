# ─── RANGER V3 START: 09-live-console ───
"""
F09 2a: the tenancy test is the point. A broadcast to org A reaches A's socket
and NOTHING reaches org B's.

Runs against the real ASGI `application` (origin validator + router +
consumer), with the in-memory channel layer so Redis is not required.

transaction=True: database_sync_to_async runs on another thread with its own
DB connection, which cannot see rows inside the default test transaction.
"""
from datetime import timedelta

import pytest
import pytest_asyncio
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.db import connections
from rest_framework_simplejwt.tokens import AccessToken

from ranger_backend.asgi import application
from ros_bridge.broadcast import broadcast_sensorlog, dashboard_group
from ros_bridge.consumers import (
    CLOSE_NO_ORG,
    CLOSE_UNAUTHENTICATED,
    SUBPROTOCOL,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db(transaction=True)]

PATH = "/ws/dashboard/"
ORIGIN = [(b"origin", b"http://localhost:5173")]


@pytest.fixture(autouse=True)
def in_memory_layer(settings):
    settings.CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


@pytest_asyncio.fixture(autouse=True)
async def close_worker_db_connections():
    """database_sync_to_async leaves a connection open on its worker thread;
    without this, the test DB can't be dropped at session end."""
    yield
    await sync_to_async(connections.close_all)()


def _user(username, org):
    return get_user_model().objects.create_user(
        username=username, password="Pw-for-tests-1234!", organization=org
    )


def _token(user, **exp):
    t = AccessToken.for_user(user)
    if exp:
        t.set_exp(lifetime=timedelta(**exp))
    return str(t)


def _sock(token=None, protocols=None):
    if protocols is None:
        protocols = [SUBPROTOCOL] + ([f"jwt.{token}"] if token else [])
    return WebsocketCommunicator(application, PATH, headers=ORIGIN, subprotocols=protocols)


async def _closed_with(sock):
    connected, _ = await sock.connect()
    assert connected, "consumer must accept before closing so the code reaches the browser"
    msg = await sock.receive_output(timeout=2)
    assert msg["type"] == "websocket.close"
    await sock.wait()  # let the consumer finish; avoids dangling layer tasks
    return msg["code"]


async def test_broadcast_reaches_own_org_only(org, other_org, sensor_log_at):
    token_a = await sync_to_async(lambda: _token(_user("alice", org)))()
    token_b = await sync_to_async(lambda: _token(_user("bob", other_org)))()

    a, b = _sock(token_a), _sock(token_b)
    ok_a, proto_a = await a.connect()
    ok_b, _ = await b.connect()
    assert ok_a and ok_b
    assert proto_a == SUBPROTOCOL

    # The real helper, from a real saved row in org A.
    log = await sync_to_async(lambda: sensor_log_at(-1.2864, 36.8172))()
    await sync_to_async(broadcast_sensorlog)(log)

    msg = await a.receive_json_from(timeout=2)
    assert msg["id"] == log.pk
    assert msg["robot"] == "TEST-BOT-001"
    assert msg["source"] == "simulated"
    assert msg["lat"] == pytest.approx(-1.2864)
    assert msg["lon"] == pytest.approx(36.8172)
    assert msg["ts"].endswith("Z")

    assert await b.receive_nothing(timeout=0.5), "org B received org A's data"

    await a.disconnect()
    await b.disconnect()


async def test_disconnect_leaves_group(org):
    token = await sync_to_async(lambda: _token(_user("alice", org)))()
    a = _sock(token)
    assert (await a.connect())[0]
    await a.disconnect()
    await a.wait()
    # Must not raise or deliver to a dead channel.
    from channels.layers import get_channel_layer
    await get_channel_layer().group_send(
        dashboard_group(org.id), {"type": "sensorlog.message", "payload": {}}
    )


async def test_no_token_closes_4401():
    assert await _closed_with(_sock()) == CLOSE_UNAUTHENTICATED


async def test_garbage_token_closes_4401():
    assert await _closed_with(_sock("not.a.jwt")) == CLOSE_UNAUTHENTICATED


async def test_expired_token_closes_4401(org):
    token = await sync_to_async(lambda: _token(_user("alice", org), seconds=-1))()
    assert await _closed_with(_sock(token)) == CLOSE_UNAUTHENTICATED


async def test_inactive_user_closes_4401(org):
    def make():
        u = _user("alice", org)
        u.is_active = False
        u.save()
        return _token(u)
    token = await sync_to_async(make)()
    assert await _closed_with(_sock(token)) == CLOSE_UNAUTHENTICATED


async def test_user_without_org_closes_4403():
    token = await sync_to_async(lambda: _token(_user("staff", None)))()
    assert await _closed_with(_sock(token)) == CLOSE_NO_ORG


async def test_token_in_query_string_is_not_accepted(org):
    """The URL is never an auth channel: it ends up in access logs."""
    token = await sync_to_async(lambda: _token(_user("alice", org)))()
    sock = WebsocketCommunicator(
        application, f"{PATH}?token={token}", headers=ORIGIN, subprotocols=[SUBPROTOCOL]
    )
    assert await _closed_with(sock) == CLOSE_UNAUTHENTICATED
# ─── RANGER V3 END: 09-live-console ───
