# ─── RANGER V3 START: 15-sim-route ───
"""Write a mission's waypoints, in order, as GeoJSON for nmea_sim --route (F15 fork 6).

    python manage.py mission_route 12 --out /home/brian/route_12.geojson

GeoJSON coordinates are [lon, lat] by spec, so nothing here or in nmea_sim
is a typed lat/lon pair to swap. One waypoint -> Point; more -> LineString.
Every waypoint is written whatever its status: the sim walks the plan, and
the platform decides what that completes.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from missions.models import Mission


def route_geojson(mission):
    coords = [[w.location.x, w.location.y] for w in mission.waypoints.order_by("order")]
    if not coords:
        raise CommandError(f"Mission {mission.pk} has no waypoints")
    geom = {"type": "Point", "coordinates": coords[0]} if len(coords) == 1 else \
        {"type": "LineString", "coordinates": coords}
    return {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "mission_id": mission.pk,
                "name": mission.name,
                "robot_id_str": mission.robot.robot_id_str,
                "threshold_m": mission.threshold_m,
                "waypoints": len(coords),
            },
        }],
    }


class Command(BaseCommand):
    help = "Export a mission's ordered waypoints as GeoJSON (for robot/tools/nmea_sim.py --route)."

    def add_arguments(self, parser):
        parser.add_argument("mission_id", type=int)
        parser.add_argument("--out", required=True, help="absolute path of the .geojson to write")

    def handle(self, *args, **opts):
        mission = Mission.objects.select_related("robot").filter(pk=opts["mission_id"]).first()
        if mission is None:
            raise CommandError(f"No mission {opts['mission_id']}")
        gj = route_geojson(mission)
        out = Path(opts["out"])
        out.write_text(json.dumps(gj, indent=1) + "\n")
        n = gj["features"][0]["properties"]["waypoints"]
        self.stdout.write(f"mission {mission.pk} '{mission.name}' [{mission.status}] "
                          f"{mission.robot.robot_id_str}: {n} waypoints -> {out}")
# ─── RANGER V3 END: 15-sim-route ───
