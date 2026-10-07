# ─── RANGER V3 START: 11-ingest-region ───
"""
F11 3b: ros_ingest --region. Runs the real handle() — arg parsing, region
resolution, banner, provenance_note, the ingest loop, point_from_latlon —
with rosbridge and the inbox faked, so no Orin, no Redis, no 1 s waits.
"""
import ast
import io
import time
from collections import Counter

import pytest
from django.core.management import CommandError, call_command

from core.geo import RABAT_VENUE
from core.models import SensorLog
from ros_bridge.management.commands import ros_ingest as mod

pytestmark = pytest.mark.django_db

NAIROBI = (-1.2864, 36.8172)          # nmea_sim's Nairobi origin
RABAT = RABAT_VENUE                   # (34.02, -6.84), N/W
RABAT_SWAPPED = (RABAT[1], RABAT[0])  # (-6.84, 34.02) — Tanzania


def _fix(lat, lon):
    t = time.time()
    return {
        "header": {"stamp": {"sec": int(t), "nanosec": int((t % 1) * 1e9)}},
        "status": {"status": 0},
        "latitude": lat,
        "longitude": lon,
    }


class FakeRos:
    instances = []

    def __init__(self, host, port):
        FakeRos.instances.append(self)
        self.is_connected = True

    def run(self, timeout):
        pass

    def terminate(self):
        pass


class FakeTopic:
    def __init__(self, client, name, msg_type):
        pass

    def subscribe(self, cb):
        pass

    def unsubscribe(self):
        pass


@pytest.fixture
def run(monkeypatch, robot):
    """run(*fixes, **opts) -> (stdout, stderr). The inbox yields the given
    fixes, then Ctrl-C — so handle()'s finally block (Stopped. {...}) runs."""
    FakeRos.instances = []
    monkeypatch.setattr(mod.roslibpy, "Ros", FakeRos)
    monkeypatch.setattr(mod.roslibpy, "Topic", FakeTopic)
    monkeypatch.setattr(mod, "close_old_connections", lambda: None)
    monkeypatch.setattr(mod, "broadcast_sensorlog", lambda log: None)

    def _run(*fixes, **opts):
        pending = list(fixes)

        class ScriptedInbox:
            def __init__(self, maxsize=0):
                pass

            def get(self, timeout=None):
                if pending:
                    return pending.pop(0)
                raise KeyboardInterrupt

            def put_nowait(self, m):
                pass

        monkeypatch.setattr(mod.queue, "Queue", ScriptedInbox)
        out, err = io.StringIO(), io.StringIO()
        call_command("ros_ingest", robot=robot.robot_id_str, stdout=out, stderr=err, **opts)
        return out.getvalue(), err.getvalue()

    return _run


def _stopped_counts(out):
    last = [ln for ln in out.splitlines() if ln.startswith("Stopped.")][-1]
    return Counter(ast.literal_eval(last.removeprefix("Stopped. ")))


class TestRabat:

    def test_rabat_fix_lands_north_west_with_region_in_note(self, run):
        out, err = run(_fix(*RABAT), region="rabat")
        log = SensorLog.objects.get()
        assert log.location.y > 0 and log.location.x < 0
        assert log.location.y == pytest.approx(RABAT[0])
        assert log.location.x == pytest.approx(RABAT[1])
        assert log.provenance_note.endswith(" · region=rabat")
        assert "region=rabat)" in out
        assert "WARNING" not in err

    def test_nairobi_and_swapped_rabat_rejected_under_rabat(self, run):
        out, _ = run(_fix(*NAIROBI), _fix(*RABAT_SWAPPED), region="rabat")
        assert SensorLog.objects.count() == 0
        assert _stopped_counts(out) == Counter(out_of_region=2)


class TestKenyaDefault:

    def test_default_is_kenya_and_nairobi_still_saves(self, run):
        out, _ = run(_fix(*NAIROBI))
        log = SensorLog.objects.get()
        assert log.provenance_note.endswith(" · region=kenya")
        assert "region=kenya)" in out

    def test_negative_proof_rabat_under_default_saves_nothing(self, run):
        """Today's bug, kept as a guarantee: forget --region in Rabat and
        every fix is out_of_region — nothing is silently written."""
        out, _ = run(_fix(*RABAT), _fix(*RABAT), _fix(*RABAT))
        assert SensorLog.objects.count() == 0
        assert _stopped_counts(out) == Counter(out_of_region=3)


class TestNone:

    def test_none_warns_saves_anything_and_says_so(self, run):
        out, err = run(_fix(*RABAT_SWAPPED), region="none")
        assert "WARNING: --region none" in err
        log = SensorLog.objects.get()
        assert log.provenance_note.endswith(" · region=none")
        assert "region=none)" in out


class TestUnknownRegion:

    @pytest.mark.parametrize("bad", ["morocco", "Rabat", ""])
    def test_kwarg_raises_before_connecting(self, run, bad):
        with pytest.raises(CommandError, match="Unknown region"):
            run(region=bad)
        assert FakeRos.instances == []

    def test_cli_flag_rejected_by_argparse(self, run):
        with pytest.raises(CommandError, match="invalid choice"):
            call_command("ros_ingest", "--region=morocco")
        assert FakeRos.instances == []
# ─── RANGER V3 END: 11-ingest-region ───
