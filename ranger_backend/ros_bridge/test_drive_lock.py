# ─── RANGER V3 START: 14-teleop ───
"""The one-driver lease (drive_lock.py) and grant_drive, F14 5a.

Each lock test runs against the memory backend and, when a Redis server answers on
REDIS_HOST:REDIS_PORT (dev_up.sh starts one), against the real Redis backend too.
"""
import asyncio
import uuid

import pytest
import redis
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from ros_bridge.drive_lock import MemoryDriveLock, RedisDriveLock, get_drive_lock, lock_key


def _redis_up():
    try:
        return redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT,
                           socket_connect_timeout=0.5).ping()
    except redis.exceptions.RedisError:
        return False


@pytest.fixture(params=["memory", "redis"])
def lock_and_robot(request):
    MemoryDriveLock._held.clear()
    if request.param == "redis" and not _redis_up():
        pytest.skip("no Redis on REDIS_HOST:REDIS_PORT")
    robot_pk = 10_000_000 + uuid.uuid4().int % 1_000_000   # never a real robot's key
    yield (MemoryDriveLock() if request.param == "memory" else RedisDriveLock()), robot_pk
    if request.param == "redis":
        redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT).delete(lock_key(robot_pk))
    MemoryDriveLock._held.clear()


def _run(coro):
    return asyncio.run(coro)


def test_acquire_is_exclusive(lock_and_robot):
    lock, pk = lock_and_robot

    async def go():
        try:
            assert await lock.acquire(pk, "a")
            assert not await lock.acquire(pk, "b")
            assert not await lock.acquire(pk, "a")     # not re-entrant either
        finally:
            await lock.close()
    _run(go())


def test_only_the_owner_refreshes_or_releases(lock_and_robot):
    lock, pk = lock_and_robot

    async def go():
        try:
            assert await lock.acquire(pk, "a")
            assert not await lock.refresh(pk, "b")
            assert not await lock.release(pk, "b")
            assert await lock.refresh(pk, "a")
            assert await lock.release(pk, "a")
            assert await lock.acquire(pk, "b")
        finally:
            await lock.close()
    _run(go())


def test_lease_lapses_without_refresh(lock_and_robot):
    lock, pk = lock_and_robot

    async def go():
        try:
            assert await lock.acquire(pk, "a", ttl_ms=150)
            await asyncio.sleep(0.3)
            assert not await lock.refresh(pk, "a")      # lapsed: holder learns it lost
            assert await lock.acquire(pk, "b")
        finally:
            await lock.close()
    _run(go())


def test_refresh_extends_the_lease(lock_and_robot):
    lock, pk = lock_and_robot

    async def go():
        try:
            assert await lock.acquire(pk, "a", ttl_ms=200)
            for _ in range(4):
                await asyncio.sleep(0.1)
                assert await lock.refresh(pk, "a", ttl_ms=200)
            assert not await lock.acquire(pk, "b")      # 400 ms later, still held
        finally:
            await lock.close()
    _run(go())


def test_backend_setting(settings):
    settings.TELEOP_DRIVE_LOCK = "memory"
    assert isinstance(get_drive_lock(), MemoryDriveLock)
    settings.TELEOP_DRIVE_LOCK = "redis"
    assert isinstance(get_drive_lock(), RedisDriveLock)
    settings.TELEOP_DRIVE_LOCK = "file"
    with pytest.raises(ValueError):
        get_drive_lock()


# ── grant_drive ──────────────────────────────────────────────────────────────
@pytest.mark.django_db
def test_grant_drive_command(org, capsys):
    u = get_user_model().objects.create_user(username="g", password="x", organization=org)
    call_command("grant_drive", "g")
    call_command("grant_drive", "g")                           # idempotent
    assert get_user_model().objects.get(pk=u.pk).has_perm("core.drive_robot")
    call_command("grant_drive", "g", revoke=True)
    assert not get_user_model().objects.get(pk=u.pk).has_perm("core.drive_robot")
    out = capsys.readouterr().out
    assert "g: drive_robot=True" in out and "g: drive_robot=False" in out


@pytest.mark.django_db
def test_grant_drive_unknown_user():
    with pytest.raises(CommandError, match="No user"):
        call_command("grant_drive", "nobody")
# ─── RANGER V3 END: 14-teleop ───
