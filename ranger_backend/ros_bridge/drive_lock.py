# ─── RANGER V3 START: 14-teleop ───
"""One driver per robot (F14 5a).

A lease, not a mutex: TTL_MS after the holder's last refresh it lapses by itself, so
a crashed Daphne worker cannot hold a robot forever. TeleopConsumer refreshes on every
message; the console sends a "hold" keepalive while idle.

Backends (settings.TELEOP_DRIVE_LOCK):
    "redis"   (default) shared by every Daphne process; atomic owner checks in Lua.
    "memory"  one process only: tests.
"""
import time

import redis.asyncio as aioredis
from django.conf import settings

TTL_MS = 3000

_REFRESH = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('PEXPIRE', KEYS[1], ARGV[2])
end
return 0
"""
_RELEASE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


def lock_key(robot_pk: int) -> str:
    return f"ranger:teleop:driver:{int(robot_pk)}"


class RedisDriveLock:
    """One client per consumer (connect to disconnect): a 20 Hz refresh must not open
    a TCP connection per message, and a client is bound to the event loop it was
    created on."""

    def __init__(self, url=None):
        self.url = url or f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"
        self._client = None

    def _c(self):
        if self._client is None:
            self._client = aioredis.from_url(self.url)
        return self._client

    async def acquire(self, robot_pk, owner, ttl_ms=TTL_MS) -> bool:
        return bool(await self._c().set(lock_key(robot_pk), owner, nx=True, px=ttl_ms))

    async def refresh(self, robot_pk, owner, ttl_ms=TTL_MS) -> bool:
        return bool(await self._c().eval(_REFRESH, 1, lock_key(robot_pk), owner, ttl_ms))

    async def release(self, robot_pk, owner) -> bool:
        return bool(await self._c().eval(_RELEASE, 1, lock_key(robot_pk), owner))

    async def close(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None


class MemoryDriveLock:
    """Same semantics, one process. Tests only."""

    _held: dict = {}   # class-level: shared by every consumer in the process

    def __init__(self, clock=time.monotonic):
        self.clock = clock

    def _live(self, key):
        entry = self._held.get(key)
        if entry and self.clock() >= entry[1]:
            del self._held[key]
            return None
        return entry

    async def acquire(self, robot_pk, owner, ttl_ms=TTL_MS) -> bool:
        key = lock_key(robot_pk)
        if self._live(key):
            return False
        self._held[key] = (owner, self.clock() + ttl_ms / 1000)
        return True

    async def refresh(self, robot_pk, owner, ttl_ms=TTL_MS) -> bool:
        key = lock_key(robot_pk)
        entry = self._live(key)
        if not entry or entry[0] != owner:
            return False
        self._held[key] = (owner, self.clock() + ttl_ms / 1000)
        return True

    async def release(self, robot_pk, owner) -> bool:
        key = lock_key(robot_pk)
        entry = self._live(key)
        if not entry or entry[0] != owner:
            return False
        del self._held[key]
        return True

    async def close(self):
        pass


def get_drive_lock():
    backend = getattr(settings, "TELEOP_DRIVE_LOCK", "redis")
    if backend == "memory":
        return MemoryDriveLock()
    if backend == "redis":
        return RedisDriveLock()
    raise ValueError(f"TELEOP_DRIVE_LOCK {backend!r}: expected 'redis' or 'memory'")
# ─── RANGER V3 END: 14-teleop ───
