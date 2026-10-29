# ─── RANGER V3 START: 15-mission-plan ───
"""
Mission planning API (F15 / Pass 6a): tenancy, order, inversion, edit lock.

Mutation checks (run by hand, each must turn a test red):
  * drop the org filter in views._org_missions      -> TestTenancy fails
  * drop the region check in _points_in_one_region  -> TestGeometry inversion fails
"""
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from missions.models import Mission, Waypoint

NAIROBI_ROUTE = [
    {"lat": -1.2921, "lon": 36.8219},
    {"lat": -1.2930, "lon": 36.8228},
    {"lat": -1.2940, "lon": 36.8235},
]
RABAT_POINT = {"lat": 34.02, "lon": -6.84}

LIST = reverse("mission-list")


def detail(pk):
    return reverse("mission-detail", args=[pk])


def payload(robot, waypoints=NAIROBI_ROUTE, **extra):
    return {"name": "North sweep", "description": "", "robot_id_str": robot.robot_id_str,
            "waypoints": waypoints, **extra}


@pytest.fixture
def other_client(db, other_org):
    user = get_user_model().objects.create_user(
        username="other-tenant-user", password="OtherPassword1234!", organization=other_org,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def created(authed_client, robot):
    r = authed_client.post(LIST, payload(robot), format="json")
    assert r.status_code == 201, r.data
    return r.data


@pytest.mark.geo
@pytest.mark.django_db
class TestCreate:

    def test_rows_land_in_order(self, created, org, robot):
        m = Mission.objects.get(pk=created["id"])
        assert (m.organization, m.robot, m.status) == (org, robot, Mission.Status.PENDING)
        assert m.created_by.username == "fixture-user"
        assert m.threshold_m == 5.0
        stored = [(w.order, w.latitude, w.longitude) for w in m.waypoints.order_by("order")]
        assert stored == [(i, pytest.approx(w["lat"]), pytest.approx(w["lon"]))
                          for i, w in enumerate(NAIROBI_ROUTE)]

    def test_response_echoes_lat_lon_by_name(self, created):
        assert [(w["order"], w["lat"], w["lon"]) for w in created["waypoints"]] == [
            (i, pytest.approx(w["lat"]), pytest.approx(w["lon"])) for i, w in enumerate(NAIROBI_ROUTE)
        ]
        assert all(w["status"] == "PENDING" and w["completed_at"] is None for w in created["waypoints"])

    def test_robot_pk_is_not_accepted(self, authed_client, robot):
        body = payload(robot)
        del body["robot_id_str"]
        r = authed_client.post(LIST, {**body, "robot": robot.pk}, format="json")
        assert r.status_code == 400 and "robot_id_str" in r.data

    def test_org_and_creator_ignored_in_payload(self, authed_client, robot, org, other_org):
        r = authed_client.post(LIST, payload(robot, organization=other_org.pk, created_by=999), format="json")
        assert r.status_code == 201
        assert Mission.objects.get(pk=r.data["id"]).organization == org

    def test_rabat_mission_accepted(self, authed_client, robot):
        r = authed_client.post(LIST, payload(robot, [RABAT_POINT]), format="json")
        assert r.status_code == 201, r.data

    @pytest.mark.parametrize("t,ok", [(0.5, False), (1.0, True), (50.0, True), (50.1, False)])
    def test_threshold_bounds(self, authed_client, robot, t, ok):
        r = authed_client.post(LIST, payload(robot, threshold_m=t), format="json")
        assert (r.status_code == 201) is ok, r.data

    @pytest.mark.parametrize("n,ok", [(0, False), (1, True), (50, True), (51, False)])
    def test_waypoint_count_bounds(self, authed_client, robot, n, ok):
        wps = [{"lat": -1.29 - i * 1e-4, "lon": 36.82} for i in range(n)]
        r = authed_client.post(LIST, payload(robot, wps), format="json")
        assert (r.status_code == 201) is ok
        if not ok:
            assert Mission.objects.count() == 0

    def test_db_rejects_threshold_out_of_range(self, org, robot):
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            Mission.objects.create(organization=org, robot=robot, name="x", threshold_m=0.0)


@pytest.mark.geo
@pytest.mark.django_db
class TestGeometry:

    def test_swapped_lat_lon_rejected_nothing_written(self, authed_client, robot):
        swapped = [{"lat": w["lon"], "lon": w["lat"]} for w in NAIROBI_ROUTE]
        r = authed_client.post(LIST, payload(robot, swapped), format="json")
        assert r.status_code == 400
        assert "waypoints" in r.data
        assert (Mission.objects.count(), Waypoint.objects.count()) == (0, 0)

    def test_swapped_rabat_rejected(self, authed_client, robot):
        r = authed_client.post(LIST, payload(robot, [{"lat": -6.84, "lon": 34.02}]), format="json")
        assert r.status_code == 400

    def test_mixed_regions_rejected(self, authed_client, robot):
        r = authed_client.post(LIST, payload(robot, [NAIROBI_ROUTE[0], RABAT_POINT]), format="json")
        assert r.status_code == 400
        assert Mission.objects.count() == 0

    def test_positional_pairs_rejected(self, authed_client, robot):
        r = authed_client.post(LIST, payload(robot, [[-1.2921, 36.8219]]), format="json")
        assert r.status_code == 400


@pytest.mark.geo
@pytest.mark.django_db
class TestTenancy:

    def test_other_org_list_is_empty(self, created, other_client):
        r = other_client.get(LIST)
        assert r.status_code == 200 and r.data["results"] == []

    def test_own_list_sees_it(self, created, authed_client):
        assert [m["id"] for m in authed_client.get(LIST).data["results"]] == [created["id"]]

    def test_other_org_detail_404(self, created, other_client):
        assert other_client.get(detail(created["id"])).status_code == 404

    def test_other_org_put_404_and_unchanged(self, created, other_client, other_robot):
        r = other_client.put(detail(created["id"]), payload(other_robot, name="hijack"), format="json")
        assert r.status_code == 404
        assert Mission.objects.get(pk=created["id"]).name == "North sweep"

    def test_foreign_robot_rejected(self, authed_client, other_robot):
        r = authed_client.post(LIST, payload(other_robot), format="json")
        assert r.status_code == 400 and "robot_id_str" in r.data
        assert Mission.objects.count() == 0

    def test_user_without_org_sees_nothing_and_cannot_create(self, created, api_client, robot):
        orphan = get_user_model().objects.create_user(username="orphan", password="OrphanPassword1234!")
        api_client.force_authenticate(user=orphan)
        assert api_client.get(LIST).data["results"] == []
        assert api_client.get(detail(created["id"])).status_code == 404
        assert api_client.post(LIST, payload(robot), format="json").status_code == 400

    def test_anonymous_refused(self, created):
        anon = APIClient()  # NOT api_client: authed_client is that same object
        assert anon.get(LIST).status_code == 401
        assert anon.get(detail(created["id"])).status_code == 401
        assert anon.post(LIST, {}, format="json").status_code == 401


@pytest.mark.geo
@pytest.mark.django_db
class TestUpdate:

    def test_put_reorders_and_replaces(self, created, authed_client, robot):
        new = list(reversed(NAIROBI_ROUTE))[:2]
        r = authed_client.put(detail(created["id"]),
                              payload(robot, new, name="Renamed", threshold_m=8.0), format="json")
        assert r.status_code == 200, r.data
        m = Mission.objects.get(pk=created["id"])
        assert (m.name, m.threshold_m) == ("Renamed", 8.0)
        stored = [(w.order, w.latitude, w.longitude) for w in m.waypoints.order_by("order")]
        assert stored == [(i, pytest.approx(w["lat"]), pytest.approx(w["lon"])) for i, w in enumerate(new)]

    @pytest.mark.parametrize("st", ["IN_PROGRESS", "PAUSED", "COMPLETED", "ABORTED"])
    def test_put_when_not_pending_409_unchanged(self, created, authed_client, robot, st):
        Mission.objects.filter(pk=created["id"]).update(status=st)
        r = authed_client.put(detail(created["id"]), payload(robot, [NAIROBI_ROUTE[0]], name="x"), format="json")
        assert r.status_code == 409
        m = Mission.objects.get(pk=created["id"])
        assert m.name == "North sweep" and m.waypoints.count() == 3

    def test_invalid_put_leaves_waypoints_intact(self, created, authed_client, robot):
        swapped = [{"lat": 36.8219, "lon": -1.2921}]
        r = authed_client.put(detail(created["id"]), payload(robot, swapped), format="json")
        assert r.status_code == 400
        assert Waypoint.objects.filter(mission_id=created["id"]).count() == 3

    def test_patch_not_allowed(self, created, authed_client):
        assert authed_client.patch(detail(created["id"]), {"name": "x"}, format="json").status_code == 405
# ─── RANGER V3 END: 15-mission-plan ───
