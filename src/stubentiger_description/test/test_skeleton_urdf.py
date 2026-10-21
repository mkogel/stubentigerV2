"""Description seam: the processed skeleton xacro, checked from the URDF it produces."""

import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import xacro

XACRO_FILE = Path(__file__).resolve().parents[1] / "urdf" / "stubentiger.urdf.xacro"

# Decided values (#24, "stubentiger_description"), in metres, kilograms, rad/s and N·m.
FLOOR_WHEEL_X = (0.0615, 0.0, -0.0615)
WHEEL_RADIUS = 0.01966
WHEEL_SEPARATION = 0.190
TOTAL_MASS = 2.2
WHEEL_VELOCITY_LIMIT = 48.2
STALL_TORQUE_PER_SIDE = 0.54

# Slack: geometry is exact up to float formatting; the velocity limit is "about" 48.2.
GEOMETRY_SLACK = 1e-6
VELOCITY_LIMIT_SLACK = 0.05

COMMANDED = {"left": "left_wheel_joint", "right": "right_wheel_joint"}
MIMIC = {
    "left": ("left_wheel_2_joint", "left_wheel_3_joint"),
    "right": ("right_wheel_2_joint", "right_wheel_3_joint"),
}
WHEEL_JOINTS = [j for side in ("left", "right") for j in (COMMANDED[side], *MIMIC[side])]


@pytest.fixture(scope="module")
def urdf_xml() -> str:
    return xacro.process_file(str(XACRO_FILE)).toxml()


@pytest.fixture(scope="module")
def robot(urdf_xml: str) -> ET.Element:
    return ET.fromstring(urdf_xml)


def joint(robot: ET.Element, name: str) -> ET.Element:
    found = robot.find(f"joint[@name='{name}']")
    assert found is not None, f"joint {name} is missing"
    return found


def child_link(robot: ET.Element, joint_name: str) -> str:
    child = joint(robot, joint_name).find("child")
    assert child is not None
    return child.attrib["link"]


def floats(text: str | None) -> list[float]:
    assert text is not None
    return [float(v) for v in text.split()]


def position_in_footprint(robot: ET.Element, link: str) -> list[float]:
    """Position of a link's origin relative to base_footprint (the chain has no rotations)."""
    position = [0.0, 0.0, 0.0]
    while link != "base_footprint":
        parent_joint = robot.find(f"joint/child[@link='{link}']/..")
        assert parent_joint is not None, f"{link} has no parent joint"
        origin = parent_joint.find("origin")
        assert origin is not None
        assert floats(origin.get("rpy", "0 0 0")) == [0.0, 0.0, 0.0]
        position = [p + o for p, o in zip(position, floats(origin.get("xyz", "0 0 0")))]
        parent = parent_joint.find("parent")
        assert parent is not None
        link = parent.attrib["link"]
    return position


def test_check_urdf_passes(urdf_xml: str, tmp_path: Path) -> None:
    urdf = tmp_path / "stubentiger.urdf"
    urdf.write_text(urdf_xml)
    result = subprocess.run(["check_urdf", str(urdf)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_base_is_a_box(robot: ET.Element) -> None:
    assert robot.find("link[@name='base_link']/collision/geometry/box") is not None


@pytest.mark.parametrize("side", ["left", "right"])
def test_three_floor_wheels_per_side(robot: ET.Element, side: str) -> None:
    y = WHEEL_SEPARATION / 2 if side == "left" else -WHEEL_SEPARATION / 2
    positions = []
    for name in (COMMANDED[side], *MIMIC[side]):
        positions.append(position_in_footprint(robot, child_link(robot, name)))
    assert sorted(p[0] for p in positions) == pytest.approx(
        sorted(FLOOR_WHEEL_X), abs=GEOMETRY_SLACK
    )
    for x, wheel_y, z in positions:
        assert wheel_y == pytest.approx(y, abs=GEOMETRY_SLACK)
        assert z == pytest.approx(WHEEL_RADIUS, abs=GEOMETRY_SLACK)
    assert position_in_footprint(robot, child_link(robot, COMMANDED[side]))[0] == pytest.approx(
        0.0, abs=GEOMETRY_SLACK
    )


@pytest.mark.parametrize("name", WHEEL_JOINTS)
def test_wheel_radius(robot: ET.Element, name: str) -> None:
    cylinder = robot.find(f"link[@name='{child_link(robot, name)}']/collision/geometry/cylinder")
    assert cylinder is not None
    assert float(cylinder.attrib["radius"]) == pytest.approx(WHEEL_RADIUS, abs=GEOMETRY_SLACK)


def test_total_mass(robot: ET.Element) -> None:
    masses = [float(m.attrib["value"]) for m in robot.iter("mass")]
    assert sum(masses) == pytest.approx(TOTAL_MASS, abs=GEOMETRY_SLACK)


@pytest.mark.parametrize("side", ["left", "right"])
def test_outer_wheels_mimic_the_commanded_joint(robot: ET.Element, side: str) -> None:
    assert joint(robot, COMMANDED[side]).find("mimic") is None
    for name in MIMIC[side]:
        mimic = joint(robot, name).find("mimic")
        assert mimic is not None, f"{name} is not a mimic joint"
        assert mimic.attrib["joint"] == COMMANDED[side]
        assert float(mimic.get("multiplier", "1")) == 1.0
        assert float(mimic.get("offset", "0")) == 0.0


def test_ros2_control_commands_only_the_middle_wheels(robot: ET.Element) -> None:
    joints = robot.findall("ros2_control/joint")
    assert sorted(j.attrib["name"] for j in joints) == sorted(WHEEL_JOINTS)
    for j in joints:
        commands = [c.attrib["name"] for c in j.findall("command_interface")]
        expected = ["velocity"] if j.attrib["name"] in COMMANDED.values() else []
        assert commands == expected, j.attrib["name"]
        states = sorted(s.attrib["name"] for s in j.findall("state_interface"))
        assert states == ["position", "velocity"], j.attrib["name"]


@pytest.mark.parametrize("name", WHEEL_JOINTS)
def test_wheel_joint_limits(robot: ET.Element, name: str) -> None:
    limit = joint(robot, name).find("limit")
    assert limit is not None, f"{name} has no limit"
    assert float(limit.attrib["velocity"]) == pytest.approx(
        WHEEL_VELOCITY_LIMIT, abs=VELOCITY_LIMIT_SLACK
    )
    # The side's stall torque is shared by its three floor wheels.
    effort_per_side = float(limit.attrib["effort"]) * 3
    assert effort_per_side == pytest.approx(STALL_TORQUE_PER_SIDE, abs=GEOMETRY_SLACK)
