# ─── RANGER V3 START: seed_marsabit tests ───
"""Marsabit ground-data seeding (F10.2 CP3).

Two things under test, in order of importance:

1. HONESTY. Every generated row is labelled MODELLED and carries a citation.
   Nothing is ever labelled reported or live. If this suite goes green while
   that is false, the platform's central claim is false too.

2. FIDELITY. The generated clouds match the report's published statistics
   closely enough to be a fair representation, and Forole in particular is
   background-with-isolated-anomalies rather than broadly hot.

Runs at --scale 0.05 throughout: ~600 rows is enough to assert distribution
shape without spending 12,081 inserts per test.
"""
import math

import pytest
from django.core.management import call_command

from django.contrib.auth import get_user_model

from core.management.commands.seed_marsabit import DEMO_GROUP, DEMO_USER
from core.marsabit import SITES, SITES_BY_CODE
from core.models import RadiationLog, Robot, SensorLog
from missions.models import Mission
from accounts.models import Organization

User = get_user_model()

SCALE = 0.05
ANOMALY_THRESHOLD = 300.0


@pytest.fixture
def seeded(db):
    call_command("seed_marsabit", "--scale", str(SCALE), "--seed", "42", verbosity=0)
    return Organization.objects.get(slug="knra")


def _doses(site_code):
    """Dose rates in nSv/h for one site."""
    return [
        r.dose_rate_usvh * 1000.0
        for r in RadiationLog.objects.filter(
            sensor_log__mission__metadata__site_code=site_code
        )
    ]


@pytest.mark.django_db
class TestProvenanceIsNeverOverclaimed:
    """The tests that matter most."""

    def test_every_row_is_modelled(self, seeded):
        assert SensorLog.objects.filter(robot__organization=seeded).exists()
        sources = set(
            SensorLog.objects.filter(robot__organization=seeded)
            .values_list("source", flat=True)
        )
        assert sources == {SensorLog.Source.MODELLED}

    def test_nothing_claims_to_be_measured(self, seeded):
        assert not SensorLog.objects.filter(
            robot__organization=seeded,
            source__in=[SensorLog.Source.LIVE, SensorLog.Source.REPORTED],
        ).exists()

    def test_every_row_carries_a_citation(self, seeded):
        for log in SensorLog.objects.filter(robot__organization=seeded)[:50]:
            assert "KNRA" in log.provenance_note
            assert "Modelled" in log.provenance_note

    def test_is_measured_is_false(self, seeded):
        log = SensorLog.objects.filter(robot__organization=seeded).first()
        assert log.is_measured is False

    def test_simulated_nairobi_data_is_untouched(self, seeded):
        """Seeding one tenant must not relabel another's rows."""
        other = SensorLog.objects.exclude(robot__organization=seeded)
        assert not other.filter(source=SensorLog.Source.MODELLED).exists()


@pytest.mark.django_db
class TestPlatformObjects:

    def test_creates_the_knra_tenant(self, seeded):
        assert seeded.name.startswith("Kenya Nuclear")

    def test_instruments_are_modelled_as_robots(self, seeded):
        ids = set(
            Robot.objects.filter(organization=seeded)
            .values_list("robot_id_str", flat=True)
        )
        assert {"KNRA-PGIS-2-1", "KNRA-BGEIGIE-NANO"} <= ids

    def test_one_mission_per_site_with_an_aoi(self, seeded):
        missions = Mission.objects.filter(organization=seeded)
        assert missions.count() == len(SITES)
        for mission in missions:
            assert mission.area_of_interest is not None, mission.name
            assert mission.area_of_interest.srid == 4326

    def test_points_fall_inside_their_mission_aoi(self, seeded):
        """The check the API contract diff could never make: a point in the
        wrong site's polygon is invisible until a correlation returns nothing."""
        for mission in Mission.objects.filter(organization=seeded):
            logs = SensorLog.objects.filter(mission=mission)
            assert logs.exists()
            outside = logs.exclude(location__within=mission.area_of_interest)
            assert not outside.exists(), f"{outside.count()} points outside {mission.name}"

    def test_is_idempotent_with_clear(self, seeded):
        before = SensorLog.objects.filter(robot__organization=seeded).count()
        call_command("seed_marsabit", "--scale", str(SCALE), "--seed", "42",
                     "--clear", verbosity=0)
        assert SensorLog.objects.filter(robot__organization=seeded).count() == before

    def test_same_seed_reproduces_the_same_data(self, seeded):
        first = sorted(_doses("forole"))
        call_command("seed_marsabit", "--scale", str(SCALE), "--seed", "42",
                     "--clear", verbosity=0)
        assert sorted(_doses("forole")) == pytest.approx(first)

    def test_single_site_flag(self, db):
        call_command("seed_marsabit", "--scale", str(SCALE), "--site", "forole",
                     verbosity=0)
        assert Mission.objects.filter(organization__slug="knra").count() == 1


@pytest.mark.django_db
class TestDistributionFidelity:

    @pytest.mark.parametrize("code", [s["code"] for s in SITES])
    def test_mean_matches_published(self, seeded, code):
        doses = _doses(code)
        published = SITES_BY_CODE[code]["mean"]
        actual = sum(doses) / len(doses)
        # 15% band: sampling noise at scale 0.05 is real, and matching to the
        # decimal would be fitting noise rather than shape.
        assert actual == pytest.approx(published, rel=0.15), (
            f"{code}: {actual:.1f} vs published {published}"
        )

    @pytest.mark.parametrize("code", [s["code"] for s in SITES])
    def test_values_stay_within_published_bounds(self, seeded, code):
        doses = _doses(code)
        site = SITES_BY_CODE[code]
        assert min(doses) >= site["min"] - 0.5
        assert max(doses) <= site["max"] + 0.5

    def test_forole_is_background_with_isolated_anomalies(self, seeded):
        """The report describes Forole's >300 nSv/h readings as rare and
        spatially limited. A cloud where 20% of points are anomalous would
        misrepresent the site — and would be the kind of overstatement that
        destroys credibility with anyone who has read the survey."""
        doses = _doses("forole")
        fraction = sum(1 for d in doses if d > ANOMALY_THRESHOLD) / len(doses)
        assert 0.0 < fraction < 0.06, f"{fraction:.1%} above anomaly threshold"

    def test_forole_reaches_the_published_extreme(self, seeded):
        """Isolated readings past 1 uSv/h are the survey's headline finding.
        A generated cloud that never gets there under-represents the site."""
        assert max(_doses("forole")) > 500.0

    def test_control_site_has_no_anomalies(self, seeded):
        """Balesa is the control. Any method that finds disturbance here is
        detecting something other than site disturbance."""
        assert max(_doses("balesa")) <= SITES_BY_CODE["balesa"]["max"] + 0.5

    def test_relative_site_ordering_is_preserved(self, seeded):
        """Forole hottest, Boji coolest — the report's headline comparison."""
        means = {
            code: sum(_doses(code)) / len(_doses(code))
            for code in ("forole", "boji", "balesa")
        }
        assert means["forole"] > means["balesa"] > means["boji"]

    def test_cpm_is_consistent_with_dose_rate(self, seeded):
        """radiation_value is back-calculated from dose rate, not independent."""
        from core.marsabit import CPM_PER_USVH

        for reading in RadiationLog.objects.filter(
            sensor_log__robot__organization=seeded
        )[:50]:
            assert reading.radiation_value == pytest.approx(
                reading.dose_rate_usvh * CPM_PER_USVH, rel=1e-3
            )
@pytest.mark.django_db
class TestTenantHasALogin:
    """F10.3 CP0.2.

    seed_marsabit used to create an org, two instruments, seven missions and
    12,081 rows that nobody could log in and look at. The account was made by
    hand in admin on 2026-08-06, which does not survive `--create-db` or a
    database rebuild — and there is at least one of each before the pitch.

    A seeded tenant nobody can enter is not a seeded tenant.
    """

    def test_creates_a_user_for_the_knra_org(self, seeded):
        user = User.objects.get(username=DEMO_USER)
        assert user.organization_id == seeded.id

    def test_user_is_in_the_operator_group(self, seeded):
        user = User.objects.get(username=DEMO_USER)
        assert user.groups.filter(name=DEMO_GROUP).exists()

    def test_default_password_authenticates(self, seeded):
        from django.contrib.auth import authenticate
        from accounts.management.commands.seed_demo import DEMO_PASSWORD

        assert authenticate(username=DEMO_USER, password=DEMO_PASSWORD) is not None

    def test_password_flag_is_honoured(self, db):
        from django.contrib.auth import authenticate

        call_command("seed_marsabit", "--scale", str(SCALE), "--seed", "42",
                     "--password", "TestPassword123!", verbosity=0)
        assert authenticate(
            username=DEMO_USER, password="TestPassword123!"
        ) is not None

    def test_reseeding_does_not_duplicate_the_user(self, seeded):
        call_command("seed_marsabit", "--scale", str(SCALE), "--seed", "42",
                     "--clear", verbosity=0)
        assert User.objects.filter(username=DEMO_USER).count() == 1

    def test_existing_user_password_is_untouched_by_default(self, seeded):
        """Follows seed_demo: an existing account may be a real one."""
        from django.contrib.auth import authenticate

        user = User.objects.get(username=DEMO_USER)
        user.set_password("SomethingAnOperatorChose!")
        user.save(update_fields=["password"])

        call_command("seed_marsabit", "--scale", str(SCALE), "--seed", "42",
                     "--clear", verbosity=0)
        assert authenticate(
            username=DEMO_USER, password="SomethingAnOperatorChose!"
        ) is not None

    def test_reset_password_flag_overrides_that(self, seeded):
        from django.contrib.auth import authenticate

        user = User.objects.get(username=DEMO_USER)
        user.set_password("Forgotten!")
        user.save(update_fields=["password"])

        call_command("seed_marsabit", "--scale", str(SCALE), "--seed", "42",
                     "--clear", "--reset-password",
                     "--password", "Recovered123!", verbosity=0)
        assert authenticate(
            username=DEMO_USER, password="Recovered123!"
        ) is not None

    def test_user_org_is_repaired_if_wrong(self, seeded):
        """A user in the right group but the WRONG org sees an empty console
        while looking perfectly configured — the worst kind of broken."""
        other = Organization.objects.create(slug="wrong-org", name="Wrong")
        user = User.objects.get(username=DEMO_USER)
        user.organization = other
        user.save(update_fields=["organization"])

        call_command("seed_marsabit", "--scale", str(SCALE), "--seed", "42",
                     "--clear", verbosity=0)
        user.refresh_from_db()
        assert user.organization_id == seeded.id
# ─── RANGER V3 END: seed_marsabit tests ───