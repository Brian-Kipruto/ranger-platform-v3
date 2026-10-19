# ─── RANGER V3 START: 14-uno-bridge ───
"""Pure logic for uno_bridge (F14 5a): the Orin side of the Uno serial contract.

No rclpy or pyserial at import, so it is tested on the PC
(ranger_backend/ros_bridge/test_uno_protocol.py), loaded by path like sensor_sources.

Contract (robot/firmware/uno_motor_geiger/uno_motor_geiger.ino, 115200 baud, '\\n' lines):
    Orin -> Uno  M,<left>,<right>     signed PWM in [-255, 255]
    Uno -> Orin  S,<ms>,<mode>,<rc_ok>,<left>,<right>,<m_age_ms>,<rc_age_ms>,
                   <ppm_rejected>,<ppm_glitches>,<ppm_disagreed>
    Uno -> Orin  G,<counts>           counts since the previous G (only with a tube)

cmd_vel is NORMALISED, not SI: linear.x and angular.z are fractions in [-1, 1] of
max_pwm (no wheel-speed calibration exists yet). REP-103 sign: +angular.z turns left.
"""
import math

PWM_LIMIT = 255
MODES = frozenset('XRNW')
S_FIELDS = ('ms', 'mode', 'rc_ok', 'left', 'right', 'm_age_ms', 'rc_age_ms',
            'ppm_rejected', 'ppm_glitches', 'ppm_disagreed')


def _unit(v):
    """A finite float clamped to [-1, 1]; None for NaN/inf (caller stops)."""
    v = float(v)
    if not math.isfinite(v):
        return None
    return max(-1.0, min(1.0, v))


def twist_to_pwm(linear_x, angular_z, max_pwm):
    """Differential mix of a normalised Twist to (left, right) PWM.

    Non-finite input stops (0, 0). The mix is scaled down, not clipped, when a side
    would exceed 1, so turning while at full speed keeps the turn ratio.
    """
    max_pwm = max(0, min(PWM_LIMIT, int(max_pwm)))
    lin, ang = _unit(linear_x), _unit(angular_z)
    if lin is None or ang is None:
        return 0, 0
    left, right = lin - ang, lin + ang
    peak = max(abs(left), abs(right))
    if peak > 1.0:
        left, right = left / peak, right / peak
    return int(round(left * max_pwm)), int(round(right * max_pwm))


def format_m(left, right):
    for v in (left, right):
        if not isinstance(v, int) or not -PWM_LIMIT <= v <= PWM_LIMIT:
            raise ValueError(f'PWM {v!r} outside [-{PWM_LIMIT}, {PWM_LIMIT}]')
    return f'M,{left},{right}\n'


def parse_line(line):
    """('S', dict) | ('G', counts) | None for anything malformed."""
    parts = line.strip().split(',')
    try:
        if parts[0] == 'G' and len(parts) == 2:
            counts = int(parts[1])
            return ('G', counts) if counts >= 0 else None
        if parts[0] == 'S' and len(parts) == 1 + len(S_FIELDS):
            vals = dict(zip(S_FIELDS, parts[1:]))
            if vals['mode'] not in MODES:
                return None
            out = {k: int(v) for k, v in vals.items() if k != 'mode'}
            out['mode'] = vals['mode']
            return ('S', out)
    except ValueError:
        return None
    return None


class CmdGate:
    """What to write to the Uno on each send tick.

    Fresh command (age <= stale_s): its M line. Stale: one M,0,0, then nothing, so the
    Uno's own 250 ms watchdog is the second, independent stop. Never commanded: nothing.
    """

    def __init__(self, stale_s):
        self.stale_s = stale_s
        self.left = self.right = 0
        self.last = None
        self.stop_sent = False
        self.stale_stop = False   # True only on the tick that sent the stale stop

    def on_cmd(self, left, right, now):
        self.left, self.right, self.last = left, right, now
        self.stop_sent = False

    def tick(self, now):
        self.stale_stop = False
        if self.last is None:
            return None
        if now - self.last <= self.stale_s:
            return format_m(self.left, self.right)
        if not self.stop_sent:
            self.stop_sent = True
            self.stale_stop = True
            return format_m(0, 0)
        return None
# ─── RANGER V3 END: 14-uno-bridge ───
