# ─── RANGER V3 START: 15-mission-advance ───
"""
Proximity advance (F15 fork 1): the ONE place waypoint completion is decided.

Every accepted, located fix for a robot is offered here. If the robot has an
IN_PROGRESS mission, the active waypoint is its first PENDING one by `order`.
A fix within the mission's `threshold_m` of it (geodesic metres, PostGIS)
completes it at the fix's own timestamp; completing the last one completes
the mission.

Rules, each pinned by a test:
  * at most one waypoint per fix, and never out of order — a fix near
    waypoint 3 while 2 is PENDING does nothing;
  * a miss changes nothing (no "closest approach" credit);
  * PENDING / PAUSED / finished missions are never advanced.

Callers MUST already be inside transaction.atomic(): the mission row is
locked so two ingest processes can't both complete the same waypoint, and
the fix row the caller writes commits with the advance or not at all.
"""
from dataclasses import dataclass

from django.contrib.gis.db.models.functions import Distance
from django.db import transaction

from .models import Mission, Waypoint


@dataclass(frozen=True)
class Advance:
    mission: Mission
    waypoint: Waypoint | None      # the active waypoint the fix was measured against
    distance_m: float | None
    completed: bool                # waypoint flipped to COMPLETED by this fix
    mission_completed: bool        # ...and it was the last one


def active_mission(robot):
    """The robot's IN_PROGRESS mission, row-locked, or None. At most one can
    exist (one_in_progress_mission_per_robot)."""
    return (
        Mission.objects.select_for_update()
        .filter(robot=robot, status=Mission.Status.IN_PROGRESS)
        .first()
    )


def advance(robot, point, ts) -> Advance | None:
    """Offer one located fix. Returns None when the robot has no running mission."""
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("missions.progress.advance must run inside transaction.atomic()")

    mission = active_mission(robot)
    if mission is None:
        return None

    wp = (
        mission.waypoints.filter(status=Waypoint.Status.PENDING)
        .order_by("order")
        .annotate(d=Distance("location", point))
        .first()
    )
    if wp is None:
        # Running with nothing left to reach (e.g. edited in admin). Leave it
        # for the operator; never silently complete a mission here.
        return Advance(mission, None, None, False, False)

    d = wp.d.m
    if d > mission.threshold_m:
        return Advance(mission, wp, d, False, False)

    wp.status = Waypoint.Status.COMPLETED
    wp.completed_at = ts
    wp.save(update_fields=["status", "completed_at"])

    last = not mission.waypoints.filter(status=Waypoint.Status.PENDING).exists()
    if last:
        mission.status = Mission.Status.COMPLETED
        mission.completed_at = ts
        mission.save(update_fields=["status", "completed_at", "updated_at"])
    return Advance(mission, wp, d, True, last)
# ─── RANGER V3 END: 15-mission-advance ───
