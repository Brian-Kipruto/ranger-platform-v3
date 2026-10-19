# ─── RANGER V3 START: 14-teleop ───
"""Teleop commands between TeleopConsumer (sender) and teleop_relay (receiver), F14 5a.

Both sides name the channel and build/check commands here, so they cannot drift
(the dashboard_group pattern, ADR-0017).

A command is a NORMALISED drive request: lin and ang are fractions in [-1, 1] of the
robot's speed cap, +ang turns left (REP-103). uno_bridge maps them to PWM.

One plain channel per robot (not a group): exactly one relay consumes it. A channel
nobody reads keeps messages until they expire, so every command carries its server
send time and the relay drops anything older than MAX_CMD_AGE_S. A relay started late
must never replay a queue of old drive commands.
"""
import math

TELEOP_CMD = "teleop.cmd"
MAX_CMD_AGE_S = 0.3        # same host, so a fresh command is milliseconds old
MAX_CLOCK_AHEAD_S = 0.05   # a command from the future is malformed, not fresh


def teleop_channel(robot_pk: int) -> str:
    # Channels names: ^[a-zA-Z0-9\-_.]+$ and < 100 chars (no colons).
    return f"teleop.robot.{int(robot_pk)}"


def _unit(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    v = float(v)
    if not math.isfinite(v) or not -1.0 <= v <= 1.0:
        return None
    return v


def make_cmd(lin, ang, sent_at: float) -> dict:
    """Raises ValueError rather than build a command the relay would drop."""
    if _unit(lin) is None or _unit(ang) is None:
        raise ValueError(f"lin/ang must be finite numbers in [-1, 1], got {lin!r}, {ang!r}")
    return {"type": TELEOP_CMD, "lin": float(lin), "ang": float(ang), "sent_at": float(sent_at)}


def validate_cmd(msg, now: float, max_age_s: float = MAX_CMD_AGE_S):
    """(lin, ang) for a well-formed, fresh command; otherwise (None, reason)."""
    if not isinstance(msg, dict) or msg.get("type") != TELEOP_CMD:
        return None, "type"
    lin, ang = _unit(msg.get("lin")), _unit(msg.get("ang"))
    if lin is None or ang is None:
        return None, "value"
    sent_at = msg.get("sent_at")
    if isinstance(sent_at, bool) or not isinstance(sent_at, (int, float)) \
            or not math.isfinite(sent_at):
        return None, "sent_at"
    age = now - sent_at
    if age > max_age_s:
        return None, "stale"
    if age < -MAX_CLOCK_AHEAD_S:
        return None, "future"
    return (lin, ang), None


def twist(lin: float, ang: float) -> dict:
    """geometry_msgs/Twist as roslibpy wants it."""
    return {"linear": {"x": lin, "y": 0.0, "z": 0.0},
            "angular": {"x": 0.0, "y": 0.0, "z": ang}}


async def relay_one(layer, channel: str, publish, clock) -> str:
    """Receive one message; publish it as a Twist if valid and fresh.

    Returns "sent" or the drop reason. Never publishes anything it did not just
    receive: no repeats, no held state. Silence downstream is the stop signal
    (uno_bridge stops 250 ms after the last cmd_vel).
    """
    msg = await layer.receive(channel)
    cmd, reason = validate_cmd(msg, clock())
    if cmd is None:
        return reason
    publish(twist(*cmd))
    return "sent"
# ─── RANGER V3 END: 14-teleop ───
