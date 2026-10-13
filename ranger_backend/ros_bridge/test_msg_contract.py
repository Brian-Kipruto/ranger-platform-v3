# ─── RANGER V3 START: 13-ranger-msgs ───
"""The robot's .msg files and readings.py describe the same messages (ADR-0020).

The vault's warning, made executable: a sensor that reads fine and a topic
that publishes fine still save nothing if a field name disagrees. Both sides
live in this repo (ADR-0014), so this test reads robot/ranger_msgs directly
and fails the commit that lets them drift — in either direction.
"""
import re

import pytest
from django.conf import settings

from ros_bridge.readings import ROBOT_CLAIMS, SPECS

PKG = settings.PROJECT_ROOT / "robot" / "ranger_msgs"
LINE = re.compile(r"^(?P<type>\S+)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?:\s*=\s*(?P<value>.+))?$")


def parse_msg(path):
    """-> (fields {name: type}, constants {NAME: value}). Comments stripped."""
    fields, consts = {}, {}
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = LINE.match(line)
        assert m, f"{path.name}: unparseable line {raw!r}"
        if m["value"] is not None:
            consts[m["name"]] = m["value"].strip().strip('"\'')
        else:
            fields[m["name"]] = m["type"]
    return fields, consts


def msg_path(spec):
    pkg, kind, name = spec.msg_type.split("/")
    assert (pkg, kind) == ("ranger_msgs", "msg"), spec.msg_type
    return PKG / "msg" / f"{name}.msg"


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.key)
class TestEachMessage:

    def test_exists_and_is_built(self, spec):
        path = msg_path(spec)
        assert path.is_file(), path
        cmake = (PKG / "CMakeLists.txt").read_text()
        assert f'"msg/{path.name}"' in cmake, f"{path.name} not in rosidl_generate_interfaces"

    def test_fields_match_both_ways(self, spec):
        """Every field ingest reads exists; every field the robot sends is read."""
        fields, _ = parse_msg(msg_path(spec))
        assert fields.pop("header", None) == "std_msgs/Header", "needs a header stamp (fork 8)"
        assert fields.pop("source", None) == "string", "needs the robot's claim (fork 7)"
        assert fields == {f: "float64" for f, _ in spec.fields}

    def test_source_constants_are_the_claims_ingest_accepts(self, spec):
        _, consts = parse_msg(msg_path(spec))
        assert consts == {"SOURCE_LIVE": "live", "SOURCE_SIMULATED": "simulated"}
        assert set(consts.values()) == set(ROBOT_CLAIMS)

    def test_topic_is_namespaced(self, spec):
        assert spec.topic.startswith("/ranger/")


def test_manifest_parses_like_colcon():
    """colcon validates package.xml with catkin_pkg before building anything.
    An invalid manifest (e.g. a maintainer email without a dotted domain) must
    fail here, on the PC, not at `colcon build` on the Orin."""
    from catkin_pkg.package import parse_package

    warnings = []
    pkg = parse_package(str(PKG / "package.xml"), warnings=warnings)
    assert warnings == []
    assert pkg.name == "ranger_msgs"
    assert pkg.get_build_type() == "ament_cmake"
    assert "rosidl_interface_packages" in [g.name for g in pkg.member_of_groups]
    assert "project(ranger_msgs)" in (PKG / "CMakeLists.txt").read_text()


def test_no_unlisted_messages():
    """A .msg nobody ingests is either dead or a forgotten SPEC."""
    on_disk = {p.stem for p in (PKG / "msg").glob("*.msg")}
    assert on_disk == {s.msg_type.rsplit("/", 1)[1] for s in SPECS}
# ─── RANGER V3 END: 13-ranger-msgs ───
