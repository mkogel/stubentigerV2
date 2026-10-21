"""Main seam, bring-up: robot.launch.py hardware:=mock under launch_testing.

The common launch brings up every node of the Teleop stack, all controllers become active,
including the gpio broadcaster, and the stack publishes /gpio_states, /odom and the
odom → base_footprint transform.
"""

import time
import unittest
from collections.abc import Callable

import launch_testing.actions
import pytest
import rclpy
from control_msgs.msg import DynamicInterfaceGroupValues
from controller_manager_msgs.srv import ListControllers
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare
from nav_msgs.msg import Odometry
from rclpy.node import Node as RclpyNode
from tf2_msgs.msg import TFMessage

NODES = (
    "robot_state_publisher",
    "controller_manager",
    "twist_mux",
    "game_controller_node",
    "teleop_twist_joy_node",
    "foxglove_bridge",
)
CONTROLLERS = ("joint_state_broadcaster", "diff_drive_controller", "gpio_state_broadcaster")
# The motor controller's telemetry, declared by the description on real and mock (#10).
GPIO = "motor_controller"
GPIO_STATES = (
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

# Guards on waiting, not bounds under test.
STARTUP_TIMEOUT = 60.0
SERVICE_CALL_TIMEOUT = 5.0


@pytest.mark.launch_test
def generate_test_description() -> LaunchDescription:
    robot = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution(
                [FindPackageShare("stubentiger_bringup"), "launch", "robot.launch.py"]
            )
        ),
        launch_arguments={"hardware": "mock"}.items(),
    )
    return LaunchDescription([robot, launch_testing.actions.ReadyToTest()])


class TestBringup(unittest.TestCase):
    node: RclpyNode

    @classmethod
    def setUpClass(cls) -> None:
        rclpy.init()
        cls.node = rclpy.create_node("test_bringup")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.node.destroy_node()
        rclpy.shutdown()

    def spin_until(self, done: Callable[[], bool], what: str) -> None:
        deadline = time.monotonic() + STARTUP_TIMEOUT
        while not done():
            if time.monotonic() > deadline:
                raise AssertionError(f"{what}: not within {STARTUP_TIMEOUT} s")
            rclpy.spin_once(self.node, timeout_sec=0.1)

    def controller_states(self) -> dict[str, str]:
        client = self.node.create_client(ListControllers, "/controller_manager/list_controllers")
        try:
            if not client.wait_for_service(timeout_sec=SERVICE_CALL_TIMEOUT):
                return {}
            future = client.call_async(ListControllers.Request())
            rclpy.spin_until_future_complete(self.node, future, timeout_sec=SERVICE_CALL_TIMEOUT)
            response = future.result()
            return {} if response is None else {c.name: c.state for c in response.controller}
        finally:
            self.node.destroy_client(client)

    def test_every_node_runs(self) -> None:
        def running() -> set[str]:
            return {name for name, _ in self.node.get_node_names_and_namespaces()}

        self.spin_until(lambda: set(NODES) <= running(), "every node running")

    def test_all_controllers_active(self) -> None:
        self.spin_until(
            lambda: all(self.controller_states().get(c) == "active" for c in CONTROLLERS),
            f"{', '.join(CONTROLLERS)} active",
        )

    def test_gpio_states_carry_the_eleven_states(self) -> None:
        received: list[DynamicInterfaceGroupValues] = []
        self.node.create_subscription(
            DynamicInterfaceGroupValues, "/gpio_states", received.append, 10
        )
        self.spin_until(lambda: bool(received), "a message on /gpio_states")

        msg = received[-1]
        self.assertEqual(list(msg.interface_groups), [GPIO])
        self.assertCountEqual(msg.interface_values[0].interface_names, GPIO_STATES)

    def test_odom_and_its_transform_publish(self) -> None:
        received: list[Odometry] = []
        self.node.create_subscription(Odometry, "/odom", received.append, 10)
        transforms: set[tuple[str, str]] = set()
        self.node.create_subscription(
            TFMessage,
            "/tf",
            lambda msg: transforms.update(
                (t.header.frame_id, t.child_frame_id) for t in msg.transforms
            ),
            10,
        )
        self.spin_until(
            lambda: bool(received) and ("odom", "base_footprint") in transforms,
            "/odom and the odom → base_footprint transform",
        )

        self.assertEqual(received[-1].header.frame_id, "odom")
        self.assertEqual(received[-1].child_frame_id, "base_footprint")
