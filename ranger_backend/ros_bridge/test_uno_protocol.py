# ─── RANGER V3 START: 14-uno-bridge ───
"""robot/uno_protocol.py on the PC: the Orin side of the Uno serial contract (F14 5a).

Loaded by path (robot code, deployed flat to ~/ranger/, no rclpy at import).
The S-line field list is pinned against the firmware's own contract comment, so the
two sides cannot drift silently.
"""
import importlib.util
import math
import re
from pathlib import Path

import pytest

ROBOT = Path(__file__).resolve().parents[2] / "robot"
FIRMWARE = ROBOT / "firmware" / "uno_motor_geiger" / "uno_motor_geiger.ino"


def _load():
    spec = importlib.util.spec_from_file_location("uno_protocol", ROBOT / "uno_protocol.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


up = _load()


# ── twist_to_pwm ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("lin, ang, expected", [
    (0.0, 0.0, (0, 0)),
    (1.0, 0.0, (120, 120)),
    (-1.0, 0.0, (-120, -120)),
    (0.5, 0.0, (60, 60)),
    (0.0, 1.0, (-120, 120)),      # REP-103: +z turns left (CCW): right side forward
    (0.0, -1.0, (120, -120)),
    (0.5, 0.25, (30, 90)),
])
def test_twist_mix(lin, ang, expected):
    assert up.twist_to_pwm(lin, ang, 120) == expected


def test_twist_scales_not_clips_keeping_turn_ratio():
    # lin 1, ang 0.5 -> raw (0.5, 1.5) -> scaled by 1.5 -> (1/3, 1)
    assert up.twist_to_pwm(1.0, 0.5, 120) == (40, 120)


def test_twist_inputs_clamped_to_unit():
    assert up.twist_to_pwm(7.0, 0.0, 120) == (120, 120)
    assert up.twist_to_pwm(-7.0, 0.0, 120) == (-120, -120)
    # Clamped before mixing: an oversized linear must not dilute the turn.
    assert up.twist_to_pwm(7.0, 0.5, 120) == up.twist_to_pwm(1.0, 0.5, 120)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_twist_non_finite_stops(bad):
    assert up.twist_to_pwm(bad, 0.0, 120) == (0, 0)
    assert up.twist_to_pwm(0.5, bad, 120) == (0, 0)


def test_max_pwm_bounded_to_firmware_range():
    assert up.twist_to_pwm(1.0, 0.0, 999) == (255, 255)
    assert up.twist_to_pwm(1.0, 0.0, -5) == (0, 0)


def test_cap_is_never_exceeded():
    for lin in (-1, -0.7, -0.3, 0, 0.3, 0.7, 1):
        for ang in (-1, -0.7, -0.3, 0, 0.3, 0.7, 1):
            left, right = up.twist_to_pwm(lin, ang, 120)
            assert abs(left) <= 120 and abs(right) <= 120


# ── format_m ────────────────────────────────────────────────────────────────
def test_format_m():
    assert up.format_m(100, -100) == "M,100,-100\n"
    assert up.format_m(-255, 255) == "M,-255,255\n"


@pytest.mark.parametrize("left, right", [(256, 0), (0, -256), (1.5, 0), ("1", 0)])
def test_format_m_refuses_what_the_firmware_would_reject(left, right):
    with pytest.raises(ValueError):
        up.format_m(left, right)


# ── parse_line ──────────────────────────────────────────────────────────────
def test_parse_s_line_from_the_bench():
    kind, s = up.parse_line("S,28073,W,1,0,0,251,15,1,1,2")
    assert kind == "S"
    assert s == {"ms": 28073, "mode": "W", "rc_ok": 1, "left": 0, "right": 0,
                 "m_age_ms": 251, "rc_age_ms": 15, "ppm_rejected": 1,
                 "ppm_glitches": 1, "ppm_disagreed": 2}


def test_parse_s_negative_and_never_seen():
    _, s = up.parse_line("S,0,X,0,-255,255,-1,-1,0,0,0\r")
    assert s["left"] == -255 and s["m_age_ms"] == -1 and s["rc_age_ms"] == -1


def test_parse_g_line():
    assert up.parse_line("G,17") == ("G", 17)


@pytest.mark.parametrize("bad", [
    "", "S", "S,1,R,1,0,0,-1,-1,0,0",          # one field short (pre-disagreed firmware)
    "S,1,R,1,0,0,-1,-1,0,0,0,9",               # one too many
    "S,1,Q,1,0,0,-1,-1,0,0,0",                 # unknown mode
    "S,1,R,x,0,0,-1,-1,0,0,0",
    ",R,1,0,0,-1,14,1,0",                      # torn line, as seen in the serial monitor
    "G", "G,", "G,-1", "G,1.5", "G,1,2",
    "ppm_probe ready", "M,1,2",
])
def test_parse_rejects(bad):
    assert up.parse_line(bad) is None


def test_s_fields_match_firmware_contract():
    src = FIRMWARE.read_text()
    m = re.search(r"Uno -> Orin\s+S,(.*?)\n\s*//\s+every", src, re.S)
    assert m, "S contract comment not found in the firmware"
    names = re.findall(r"<(\w+)>", m.group(1))
    assert tuple(names) == up.S_FIELDS


# ── CmdGate ─────────────────────────────────────────────────────────────────
def test_gate_silent_until_first_command():
    g = up.CmdGate(0.25)
    assert g.tick(0.0) is None


def test_gate_repeats_fresh_command():
    g = up.CmdGate(0.25)
    g.on_cmd(60, 60, 10.0)
    assert g.tick(10.0) == "M,60,60\n"
    assert g.tick(10.25) == "M,60,60\n"           # inclusive


def test_gate_one_stop_then_silence():
    g = up.CmdGate(0.25)
    g.on_cmd(60, 60, 10.0)
    assert g.tick(10.2501) == "M,0,0\n" and g.stale_stop
    assert g.tick(10.30) is None and not g.stale_stop
    assert g.tick(99.0) is None


def test_gate_resumes_after_stop():
    g = up.CmdGate(0.25)
    g.on_cmd(60, 60, 10.0)
    g.tick(11.0)
    g.on_cmd(-30, 30, 12.0)
    assert g.tick(12.05) == "M,-30,30\n" and not g.stale_stop
    assert g.tick(12.3) == "M,0,0\n" and g.stale_stop


def test_gate_explicit_zero_is_not_a_stale_stop():
    g = up.CmdGate(0.25)
    g.on_cmd(0, 0, 10.0)
    assert g.tick(10.1) == "M,0,0\n" and not g.stale_stop
# ─── RANGER V3 END: 14-uno-bridge ───
