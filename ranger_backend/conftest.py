# ─── RANGER V3 START: shared test fixtures ───
"""
Project-wide pytest fixtures.

The centrepiece is `sensor_log_at` — a factory that places a SensorLog at an
exact coordinate. F10.1 uses it to prove geometry round-trips; F10.4's
correlation engine needs precisely the same thing (ground points at known
positions inside a known satellite footprint), so it is written here as a
reusable factory rather than inline setup in one test module.

Every fixture that writes a position goes through core.geo.point_from_latlon,
the same helper the simulator and future ingestion paths use. If that helper
ever regresses, these tests fail — which is the point.

Note on the test database: Django creates test_ranger_v3 and applies
core.0003_enable_postgis into it, so the connecting role must be superuser.
The Postgres image grants that to POSTGRES_USER, so `ranger` qualifies.
"""
import pytest
from django.utils import timezone

from accounts.models import Organization
from core.geo import point_from_latlon
from core.models import (
    AirQualityLog,
    ImuBaroLog,
    RadiationLog,
    Robot,
    SensorLog,
    SensorType,
)
from missions.models import Mission, Waypoint

# The simulator's default random-walk origin. Tests that need "somewhere real
# in Kenya" use this so failures read as recognisable coordinates.
NAIROBI_LAT = -1.2921
NAIROBI_LON = 36.8219


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Org", slug="test-org")


@pytest.fixture
def other_org(db):
    """A second tenant, for asserting org-scoped isolation (ADR-0006)."""
    return Organization.objects.create(name="Other Org", slug="other-org")


@pytest.fixture
def sensor_types(db):
    """The three codes run_simulation knows how to generate."""
    return {
        code: SensorType.objects.create(name=name, code=code, unit=unit)
        for code, name, unit in (
            ("geiger", "Geiger Counter", "CPM"),
            ("pm", "Particulate Matter", "ug/m3"),
            ("imu_baro", "IMU + Barometer", "mixed"),
        )
    }


@pytest.fixture
def robot(db, org, sensor_types):
    """A robot with geiger + pm installed — deliberately NOT imu_baro.

    Mirrors RANGER-PRIME-001 in the real data, where ImuBaroLog count is 0.
    That absence is what exercises the serializer's null-safe reading access.
    """
    bot = Robot.objects.create(
        organization=org,
        name="Test Bot",
        robot_id_str="TEST-BOT-001",
    )
    bot.installed_sensors.add(sensor_types["geiger"], sensor_types["pm"])
    return bot


@pytest.fixture
def other_robot(db, other_org):
    return Robot.objects.create(
        organization=other_org,
        name="Other Bot",
        robot_id_str="OTHER-BOT-001",
    )


@pytest.fixture
def mission(db, org, robot):
    return Mission.objects.create(
        organization=org,
        robot=robot,
        name="Test Mission",
        status=Mission.Status.IN_PROGRESS,
    )


@pytest.fixture
def sensor_log_at(db, robot):
    """Factory: place a SensorLog at an exact (lat, lon).

    Usage:
        log = sensor_log_at(-1.2921, 36.8219)
        log = sensor_log_at(-1.30, 36.82, radiation=42.0, pm25=18.5)
        log = sensor_log_at(-1.30, 36.82, robot=other_robot, mission=m)

    Returns the SensorLog with any requested reading rows attached. Reading
    rows are only created when a value is passed, so the default log has none
    — matching the simulator's behaviour for a robot with no matching codes.
    """
    def _make(lat, lon, *, robot=robot, mission=None, timestamp=None,
              radiation=None, pm25=None, pm10=None, altitude=None):
        log = SensorLog.objects.create(
            robot=robot,
            mission=mission,
            timestamp=timestamp or timezone.now(),
            location=point_from_latlon(lat=lat, lon=lon),
        )
        if radiation is not None:
            RadiationLog.objects.create(
                sensor_log=log,
                radiation_value=radiation,
                dose_rate_usvh=round(radiation * 0.0057, 4),
            )
        if pm25 is not None or pm10 is not None:
            AirQualityLog.objects.create(sensor_log=log, pm25=pm25, pm10=pm10)
        if altitude is not None:
            ImuBaroLog.objects.create(sensor_log=log, altitude_baro=altitude)
        return log

    return _make


@pytest.fixture
def waypoint_at(db, mission):
    """Factory: place a Waypoint at an exact (lat, lon)."""
    def _make(lat, lon, *, order=0, mission=mission):
        return Waypoint.objects.create(
            mission=mission,
            order=order,
            location=point_from_latlon(lat=lat, lon=lon),
        )
    return _make


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient
    return APIClient()


@pytest.fixture
def authed_client(api_client, org):
    """An APIClient authenticated as a user belonging to `org`."""
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.create_user(
        username="fixture-user",
        password="FixturePassword1234!",
        organization=org,
    )
    api_client.force_authenticate(user=user)
    return api_client
# ─── RANGER V3 END: shared test fixtures ───
