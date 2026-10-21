"""Description seam: the processed xacro for each hardware backend, checked from its URDF."""

import math
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import xacro
from ament_index_python.packages import get_package_share_directory

XACRO_FILE = Path(__file__).resolve().parents[1] / "urdf" / "stubentiger.urdf.xacro"

BACKENDS = ("gazebo", "real", "mock")
PLUGINS = {
    "gazebo": "gz_ros2_control/GazeboSimSystem",
    "real": "stubentiger_hardware/StubentigerSystem",
    "mock": "mock_components/GenericSystem",
}

# Decided values (#24, "stubentiger_description"), in metres, kilograms, rad/s and N·m.
FLOOR_WHEEL_X = (0.0615, 0.0, -0.0615)
WHEEL_RADIUS = 0.01966
WHEEL_SEPARATION = 0.190
TOTAL_MASS = 2.2
WHEEL_VELOCITY_LIMIT = 48.2
STALL_TORQUE_PER_SIDE = 0.54
CENTRE_OF_MASS = (-0.010, 0.0, 0.070)
CHASSIS_LOWER = (-0.0925, -0.0695, 0.055)
CHASSIS_UPPER = (0.1025, 0.0695, 0.118)
# REP-105 frames: (link, parent, position relative to base_footprint), all level.
FRAMES = (
    ("base_link", "base_footprint", (0.0, 0.0, 0.027)),
    ("lidar_link", "base_link", (0.0295, -0.028, 0.165)),  # yaw 0 until bring-up measures it
    ("imu_link", "base_link", (0.0, 0.0, 0.118)),  # placeholder until the IMU is mounted
    ("camera_link", "base_link", (0.1225, 0.0, 0.080)),
)
OPTICAL_RPY = (-math.pi / 2, 0.0, -math.pi / 2)
CAD_MESHES = ("cover_plate.stl", "sensor_plate.stl")
# Sim sensors: (link the sensor sits on, the frame ID it publishes in). A Gazebo camera looks
# along its link's x axis, so it sits on the level camera_link and publishes in the optical frame.
SENSOR_FRAMES = {
    "gpu_lidar": ("lidar_link", "lidar_link"),
    "imu": ("imu_link", "imu_link"),
    "camera": ("camera_link", "camera_optical_link"),
}
LIDAR_RATE = 5.5  # Hz
LIDAR_RANGE = (0.15, 12.0)  # m

# Slack: geometry is exact up to float formatting; the velocity limit is "about" 48.2, and the
# centre of mass "about" (−10, 0, 70) mm.
GEOMETRY_SLACK = 1e-6
VELOCITY_LIMIT_SLACK = 0.05
CENTRE_OF_MASS_SLACK = 0.001

COMMANDED = {"left": "left_wheel_joint", "right": "right_wheel_joint"}
MIMIC = {
    "left": ("left_wheel_2_joint", "left_wheel_3_joint"),
    "right": ("right_wheel_2_joint", "right_wheel_3_joint"),
}
WHEEL_JOINTS = [j for side in ("left", "right") for j in (COMMANDED[side], *MIMIC[side])]

# The motor controller's telemetry (#10, "gpio states"), all double.
TELEMETRY_STATES = (
    "battery_voltage",
    "motor_current_left",
    "motor_current_right",
    "motor_power",
    "faults",
    "trip_count",
    "last_trip",
    "firmware_sha",
    "protocol_major",
    "protocol_minor",
    "reset_cause",
)


def process(**args: str) -> str:
    return xacro.process_file(str(XACRO_FILE), mappings=args).toxml()


@pytest.fixture(scope="module", params=BACKENDS)
def hardware(request: pytest.FixtureRequest) -> str:
    return request.param


@pytest.fixture(scope="module")
def urdf_xml(hardware: str) -> str:
    return process(hardware=hardware)


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


def parent_joint(robot: ET.Element, link: str) -> ET.Element:
    found = robot.find(f"joint/child[@link='{link}']/..")
    assert found is not None, f"{link} has no parent joint"
    return found


def parent_link(robot: ET.Element, link: str) -> str:
    parent = parent_joint(robot, link).find("parent")
    assert parent is not None
    return parent.attrib["link"]


def floats(text: str | None) -> list[float]:
    assert text is not None
    return [float(v) for v in text.split()]


def position_in_footprint(robot: ET.Element, link: str) -> list[float]:
    """Position of a link's origin relative to base_footprint (the chain has no rotations)."""
    position = [0.0, 0.0, 0.0]
    while link != "base_footprint":
        origin = parent_joint(robot, link).find("origin")
        assert origin is not None
        assert floats(origin.get("rpy", "0 0 0")) == [0.0, 0.0, 0.0]
        position = [p + o for p, o in zip(position, floats(origin.get("xyz", "0 0 0")))]
        link = parent_link(robot, link)
    return position


def ros2_control(robot: ET.Element) -> ET.Element:
    blocks = robot.findall("ros2_control")
    assert len(blocks) == 1, f"expected one <ros2_control>, found {len(blocks)}"
    return blocks[0]


def test_check_urdf_passes(urdf_xml: str, tmp_path: Path) -> None:
    urdf = tmp_path / "stubentiger.urdf"
    urdf.write_text(urdf_xml)
    result = subprocess.run(["check_urdf", str(urdf)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_hardware_selects_the_plugin(robot: ET.Element, hardware: str) -> None:
    plugin = ros2_control(robot).find("hardware/plugin")
    assert plugin is not None
    assert plugin.text == PLUGINS[hardware]


def test_unknown_hardware_does_not_process() -> None:
    with pytest.raises(xacro.XacroException, match="hardware must be gazebo, real or mock"):
        process(hardware="gazbo")


def test_controllers_see_the_commanded_joints(robot: ET.Element, hardware: str) -> None:
    """real and mock expose only the commanded joints; the mimic joints are Gazebo's alone."""
    expected = WHEEL_JOINTS if hardware == "gazebo" else list(COMMANDED.values())
    joints = ros2_control(robot).findall("joint")
    assert sorted(j.attrib["name"] for j in joints) == sorted(expected)
    for j in joints:
        commands = [c.attrib["name"] for c in j.findall("command_interface")]
        expected_commands = ["velocity"] if j.attrib["name"] in COMMANDED.values() else []
        assert commands == expected_commands, j.attrib["name"]
        states = sorted(s.attrib["name"] for s in j.findall("state_interface"))
        assert states == ["position", "velocity"], j.attrib["name"]


def test_telemetry_gpio_states(robot: ET.Element, hardware: str) -> None:
    """real and mock declare the motor controller's telemetry; GazeboSimSystem ignores <gpio>."""
    gpios = ros2_control(robot).findall("gpio")
    if hardware == "gazebo":
        assert gpios == []
        return
    states = [s for g in gpios for s in g.findall("state_interface")]
    assert sorted(s.attrib["name"] for s in states) == sorted(TELEMETRY_STATES)
    for s in states:
        # Spelled out: joint_state_broadcaster and GpioCommandController skip non-double ones.
        assert s.get("data_type") == "double", s.attrib["name"]
    assert [c for g in gpios for c in g.findall("command_interface")] == []


def hardware_params(robot: ET.Element) -> dict[str, str]:
    return {p.attrib["name"]: p.text or "" for p in ros2_control(robot).findall("hardware/param")}


def test_real_takes_the_serial_port_and_counts_per_rev() -> None:
    defaults = hardware_params(ET.fromstring(process(hardware="real")))
    assert defaults["serial_port"] == "/dev/arduino"
    assert float(defaults["counts_per_rev"]) > 0

    params = hardware_params(
        ET.fromstring(process(hardware="real", serial_port="/dev/ttyACM0", counts_per_rev="1000"))
    )
    assert params["serial_port"] == "/dev/ttyACM0"
    assert float(params["counts_per_rev"]) == 1000.0


@pytest.mark.parametrize(("link", "parent", "position"), FRAMES)
def test_frame_offsets(
    robot: ET.Element, link: str, parent: str, position: tuple[float, float, float]
) -> None:
    assert parent_joint(robot, link).attrib["type"] == "fixed"
    assert parent_link(robot, link) == parent
    assert position_in_footprint(robot, link) == pytest.approx(position, abs=GEOMETRY_SLACK)


def test_camera_optical_frame(robot: ET.Element) -> None:
    """REP-103 optical frame: z forward, x right, y down, at the camera_link origin."""
    assert parent_link(robot, "camera_optical_link") == "camera_link"
    origin = parent_joint(robot, "camera_optical_link").find("origin")
    assert origin is not None
    assert floats(origin.get("xyz", "0 0 0")) == pytest.approx([0, 0, 0], abs=GEOMETRY_SLACK)
    assert floats(origin.get("rpy")) == pytest.approx(OPTICAL_RPY, abs=GEOMETRY_SLACK)


def test_chassis_collision_box(robot: ET.Element) -> None:
    collisions = robot.findall("link[@name='base_link']/collision")
    assert len(collisions) == 1
    box = collisions[0].find("geometry/box")
    assert box is not None, "the chassis collision is not a box"
    origin = collisions[0].find("origin")
    assert origin is not None
    assert floats(origin.get("rpy", "0 0 0")) == [0.0, 0.0, 0.0]
    centre = [
        b + o for b, o in zip(position_in_footprint(robot, "base_link"), floats(origin.get("xyz")))
    ]
    size = floats(box.attrib["size"])
    lower = [c - s / 2 for c, s in zip(centre, size)]
    upper = [c + s / 2 for c, s in zip(centre, size)]
    assert lower == pytest.approx(CHASSIS_LOWER, abs=GEOMETRY_SLACK)
    assert upper == pytest.approx(CHASSIS_UPPER, abs=GEOMETRY_SLACK)


def test_collision_is_primitives(robot: ET.Element) -> None:
    shapes = [list(g)[0].tag for g in robot.findall("link/collision/geometry")]
    assert shapes, "no collision geometry"
    assert set(shapes) <= {"box", "cylinder"}
    for name in WHEEL_JOINTS:
        wheel = f"link[@name='{child_link(robot, name)}']/collision/geometry/cylinder"
        assert robot.find(wheel) is not None, name


def test_visuals_use_the_cad_meshes(robot: ET.Element) -> None:
    shapes = [list(g)[0] for g in robot.findall("link/visual/geometry")]
    assert {s.tag for s in shapes} <= {"mesh", "box", "cylinder"}
    meshes = [s for s in shapes if s.tag == "mesh"]
    assert sorted(m.attrib["filename"].rsplit("/", 1)[-1] for m in meshes) == sorted(CAD_MESHES)
    for m in meshes:
        # The STLs are in millimetres.
        assert floats(m.get("scale")) == pytest.approx([0.001] * 3), m.attrib["filename"]


def test_every_mesh_path_resolves(robot: ET.Element) -> None:
    for mesh in robot.iter("mesh"):
        uri = mesh.attrib["filename"]
        assert uri.startswith("package://"), uri
        package, relative = uri.removeprefix("package://").split("/", 1)
        assert (Path(get_package_share_directory(package)) / relative).is_file(), uri


def sensors(robot: ET.Element) -> dict[str, tuple[str, ET.Element]]:
    """Each Gazebo sensor by type, with the link it is attached to."""
    found = {}
    for gazebo in robot.findall("gazebo[@reference]"):
        for sensor in gazebo.findall("sensor"):
            assert sensor.attrib["type"] not in found, f"two {sensor.attrib['type']} sensors"
            found[sensor.attrib["type"]] = (gazebo.attrib["reference"], sensor)
    return found


def test_sensors_are_off_by_default(robot: ET.Element) -> None:
    assert list(robot.iter("sensor")) == []


def test_sim_sensors() -> None:
    found = sensors(ET.fromstring(process(hardware="gazebo", sensors="true")))
    assert sorted(found) == ["camera", "gpu_lidar", "imu"]
    for sensor_type, (link, frame_id) in SENSOR_FRAMES.items():
        reference, sensor = found[sensor_type]
        assert reference == link, sensor_type
        assert sensor.findtext("gz_frame_id") == frame_id, sensor_type

    _, lidar = found["gpu_lidar"]
    assert float(lidar.findtext("update_rate", "")) == pytest.approx(LIDAR_RATE)
    assert float(lidar.findtext("lidar/range/min", "")) == pytest.approx(LIDAR_RANGE[0])
    assert float(lidar.findtext("lidar/range/max", "")) == pytest.approx(LIDAR_RANGE[1])


def test_centre_of_mass(robot: ET.Element) -> None:
    weighted = [0.0, 0.0, 0.0]
    for link in robot.findall("link[inertial]"):
        mass_element = link.find("inertial/mass")
        assert mass_element is not None
        mass = float(mass_element.attrib["value"])
        origin = link.find("inertial/origin")
        offset = floats(origin.get("xyz", "0 0 0")) if origin is not None else [0.0] * 3
        position = position_in_footprint(robot, link.attrib["name"])
        weighted = [w + mass * (p + o) for w, p, o in zip(weighted, position, offset)]
    centre = [w / TOTAL_MASS for w in weighted]
    assert centre == pytest.approx(CENTRE_OF_MASS, abs=CENTRE_OF_MASS_SLACK)


@pytest.mark.parametrize("side", ["left", "right"])
def test_three_floor_wheels_per_side(robot: ET.Element, side: str) -> None:
    y = WHEEL_SEPARATION / 2 if side == "left" else -WHEEL_SEPARATION / 2
    positions = []
    for name in (COMMANDED[side], *MIMIC[side]):
        positions.append(position_in_footprint(robot, child_link(robot, name)))
    assert sorted(p[0] for p in positions) == pytest.approx(
        sorted(FLOOR_WHEEL_X), abs=GEOMETRY_SLACK
    )
    for _, wheel_y, z in positions:
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
