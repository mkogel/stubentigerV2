"""Physics seam, Drivable sim skeleton: direct commands in headless Gazebo.

TwistStamped commands go straight to diff_drive_controller. Driving is judged on the body's true
pose from Gazebo, bridged for this test, never on /odom (which would hide slip). All time is sim
time from /clock. Every test starts from rest and measures relative to where it starts, so the
tests can run in any order on the one Gazebo instance.
"""

import math
import unittest
from collections.abc import Callable
from dataclasses import dataclass

import launch_testing.actions
import pytest
import rclpy
from builtin_interfaces.msg import Time
from controller_manager_msgs.srv import ListControllers
from geometry_msgs.msg import PoseStamped, TwistStamped
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from rclpy.node import Node as RclpyNode
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import JointState

WHEEL_JOINTS = (
    "left_wheel_joint",
    "left_wheel_2_joint",
    "left_wheel_3_joint",
    "right_wheel_joint",
    "right_wheel_2_joint",
    "right_wheel_3_joint",
)

# Decided values (#24, #28): speeds in m/s and rad/s, distances in m, times in s of sim time.
NORMAL_SPEED = 0.3
NORMAL_TURN_RATE = 1.2
STRAIGHT_DISTANCE = 1.0
STRAIGHT_DISTANCE_TOLERANCE = 0.10  # ±10 % of the distance
STRAIGHT_SIDEWAYS_MAX = 0.05
TURN_CENTRE_DRIFT_MAX = 0.05
MIXED_DURATION = 60.0
# diff_drive_controller's ramps (config/controllers.yaml in stubentiger_bringup), the robot-wide
# ceiling: the fastest a wheel speed may change is a full brake while turning, 2.0 m/s² plus
# 8.0 rad/s² at half the track separation.
LINEAR_ACCELERATION = 1.0
LINEAR_DECELERATION = 2.0
ANGULAR_DECELERATION = 8.0
WHEEL_RADIUS = 0.01966
WHEEL_SEPARATION = 0.190
WHEEL_ACCELERATION_MAX = (
    LINEAR_DECELERATION + ANGULAR_DECELERATION * WHEEL_SEPARATION / 2
) / WHEEL_RADIUS  # rad/s²
WHEEL_VELOCITY_LIMIT = 48.2  # the wheel joints' velocity limit, the motor's no-load speed

# Named slack.
DRIVES_CHECK_TIME = 1.0  # "drives": 1 s of Normal speed moves the body
DRIVES_CHECK_DISTANCE = 0.1  # more than a third of the 0.3 m it would cover without ramps
SERVICE_CALL_TIMEOUT = 5.0  # a guard on one list_controllers call, not a bound under test
# Skid steering turns slower than commanded (about 85 % here), so the turn is driven until the
# true pose has turned a full 2π, within twice the time a slip-free turn would take.
TURN_TIME_SLACK = 1.0
TURN_TIMEOUT = 2 * math.pi / NORMAL_TURN_RATE * (1 + TURN_TIME_SLACK)
WHEEL_SPEED_SLACK = 0.10  # a spike is any wheel faster than its limit + 10 %
WHEEL_SPEED_SPIKE = WHEEL_VELOCITY_LIMIT * (1 + WHEEL_SPEED_SLACK)
# DART may clamp a wheel at its velocity limit, so a jolt also counts: a wheel speed changing
# faster than the controller's ramps allow, with slack for contact and the mimic wheels' lag.
WHEEL_ACCELERATION_SLACK = 1.0
WHEEL_ACCELERATION_SPIKE = WHEEL_ACCELERATION_MAX * (1 + WHEEL_ACCELERATION_SLACK)
STARTUP_TIMEOUT = 60.0  # controllers active after the first /clock
SETTLE_TIMEOUT = 10.0  # the body comes to rest after a stop command
STILL_WINDOW = 0.5  # at rest: moved less than STILL_DISTANCE over this window
STILL_DISTANCE = 0.001
STILL_ANGLE = 0.005
COMMAND_PERIOD = 0.02  # commands at 50 Hz, the controller rate


def ramped_duration(target: float, rate: float, accel: float, decel: float) -> float:
    """How long to command `rate` so the ramped motion covers `target`.

    The ramp up loses rate²/(2·accel) against an instant start; the ramp down after the stop
    command adds rate²/(2·decel).
    """
    return (target + rate**2 / (2 * accel) - rate**2 / (2 * decel)) / rate


# Mixed driving: (linear m/s, angular rad/s, seconds), up to Turbo and the ceiling, with
# sudden reversals and pivots. 60 s in all.
MIXED_SEGMENTS = (
    (0.3, 0.0, 4.0),
    (0.6, 0.0, 4.0),
    (-0.6, 0.0, 4.0),
    (0.0, 2.5, 4.0),
    (0.0, -2.5, 4.0),
    (0.6, 2.5, 4.0),
    (-0.6, -2.5, 4.0),
    (0.3, -1.2, 4.0),
    (0.7, 0.0, 4.0),
    (0.0, 0.0, 4.0),
    (-0.3, 1.2, 4.0),
    (0.6, -2.5, 4.0),
    (0.7, 2.5, 4.0),
    (-0.7, 0.0, 4.0),
    (0.0, 1.2, 4.0),
)


@pytest.mark.launch_test
def generate_test_description() -> LaunchDescription:
    skeleton = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution(
                [FindPackageShare("stubentiger_sim"), "launch", "skeleton.launch.py"]
            )
        )
    )
    true_pose_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        arguments=["/model/stubentiger/pose@geometry_msgs/msg/PoseStamped[gz.msgs.Pose"],
    )
    return LaunchDescription([skeleton, true_pose_bridge, launch_testing.actions.ReadyToTest()])


@dataclass
class Pose2D:
    stamp: float
    x: float
    y: float
    yaw: float


def stamp_seconds(stamp: Time) -> float:
    return stamp.sec + stamp.nanosec * 1e-9


class Sim:
    """The test's view of the running sim: sim time, true pose, wheel states, commands."""

    def __init__(self, node: RclpyNode) -> None:
        self.node = node
        self.now: float | None = None
        self.poses: list[Pose2D] = []
        self.turned = 0.0  # unwrapped yaw since the last reset
        self.max_wheel_speed = 0.0
        self.max_wheel_acceleration = 0.0
        self.wheel_samples = 0
        self.non_finite: list[str] = []
        self._last_wheel: dict[str, tuple[float, float]] = {}  # name: (stamp, velocity)
        self.cmd = node.create_publisher(TwistStamped, "/diff_drive_controller/cmd_vel", 10)
        self.list_controllers = node.create_client(
            ListControllers, "/controller_manager/list_controllers"
        )
        node.create_subscription(Clock, "/clock", self._on_clock, 10)
        node.create_subscription(PoseStamped, "/model/stubentiger/pose", self._on_pose, 50)
        node.create_subscription(JointState, "/joint_states", self._on_joints, 50)

    def _on_clock(self, msg: Clock) -> None:
        self.now = stamp_seconds(msg.clock)

    def _on_pose(self, msg: PoseStamped) -> None:
        p, q = msg.pose.position, msg.pose.orientation
        values = (p.x, p.y, p.z, q.x, q.y, q.z, q.w)
        if not all(math.isfinite(v) for v in values):
            self.non_finite.append(f"true pose at {stamp_seconds(msg.header.stamp):.3f} s")
            return
        yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        if self.poses:
            step = yaw - self.poses[-1].yaw
            self.turned += math.atan2(math.sin(step), math.cos(step))
        self.poses.append(Pose2D(stamp_seconds(msg.header.stamp), p.x, p.y, yaw))
        del self.poses[:-500]

    def _on_joints(self, msg: JointState) -> None:
        # Effort is NaN by design: the wheels have no effort interface.
        stamp = stamp_seconds(msg.header.stamp)
        for name, position, velocity in zip(msg.name, msg.position, msg.velocity):
            if name not in WHEEL_JOINTS:
                continue
            if not (math.isfinite(position) and math.isfinite(velocity)):
                self.non_finite.append(f"{name} at {stamp:.3f} s")
                continue
            self.max_wheel_speed = max(self.max_wheel_speed, abs(velocity))
            last = self._last_wheel.get(name)
            if last is not None and stamp > last[0]:
                acceleration = abs(velocity - last[1]) / (stamp - last[0])
                self.max_wheel_acceleration = max(self.max_wheel_acceleration, acceleration)
            self._last_wheel[name] = (stamp, velocity)
        self.wheel_samples += 1

    def reset_wheel_stats(self) -> None:
        self.max_wheel_speed = 0.0
        self.max_wheel_acceleration = 0.0
        self.wheel_samples = 0
        self.non_finite.clear()

    def spin_until(self, done: Callable[[], bool], timeout: float, what: str) -> None:
        """Spin until `done()`, failing after `timeout` s of sim time."""
        while self.now is None:
            rclpy.spin_once(self.node, timeout_sec=0.1)
        start = self.now
        while not done():
            if self.now - start > timeout:
                raise AssertionError(f"{what}: not within {timeout} s of sim time")
            rclpy.spin_once(self.node, timeout_sec=0.01)

    def controllers_active(self) -> bool:
        if not self.list_controllers.service_is_ready():
            return False
        future = self.list_controllers.call_async(ListControllers.Request())
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=SERVICE_CALL_TIMEOUT)
        response = future.result()
        if response is None:
            return False
        states = {c.name: c.state for c in response.controller}
        return (
            states.get("joint_state_broadcaster") == "active"
            and states.get("diff_drive_controller") == "active"
        )

    def at_rest(self) -> bool:
        if not self.poses or self.poses[-1].stamp - self.poses[0].stamp < STILL_WINDOW:
            return False
        last = self.poses[-1]
        window = [p for p in self.poses if last.stamp - p.stamp <= STILL_WINDOW]
        return all(
            math.hypot(p.x - last.x, p.y - last.y) < STILL_DISTANCE
            and abs(math.atan2(math.sin(p.yaw - last.yaw), math.cos(p.yaw - last.yaw)))
            < STILL_ANGLE
            for p in window
        )

    def wait_ready_and_still(self) -> Pose2D:
        self.spin_until(self.controllers_active, STARTUP_TIMEOUT, "controllers active")
        self.spin_until(self.at_rest, SETTLE_TIMEOUT, "body at rest")
        self.turned = 0.0
        self.reset_wheel_stats()
        return self.poses[-1]

    def send(self, linear: float, angular: float) -> None:
        assert self.now is not None
        msg = TwistStamped()
        msg.header.stamp.sec = int(self.now)
        msg.header.stamp.nanosec = int((self.now - int(self.now)) * 1e9)
        msg.header.frame_id = "base_footprint"
        msg.twist.linear.x = linear
        msg.twist.angular.z = angular
        self.cmd.publish(msg)

    def drive_until(
        self, linear: float, angular: float, done: Callable[[], bool], duration: float
    ) -> bool:
        """Command a steady twist at 50 Hz until `done()` or for `duration` s of sim time.

        Does not stop; returns whether `done()` was reached.
        """
        assert self.now is not None
        end = self.now + duration
        next_command = self.now
        while self.now < end:
            if done():
                return True
            if self.now >= next_command:
                self.send(linear, angular)
                next_command += COMMAND_PERIOD
            rclpy.spin_once(self.node, timeout_sec=0.01)
        return False

    def drive(self, linear: float, angular: float, duration: float) -> None:
        self.drive_until(linear, angular, lambda: False, duration)

    def stop_and_settle(self) -> Pose2D:
        self.send(0.0, 0.0)
        self.spin_until(self.at_rest, SETTLE_TIMEOUT, "body at rest after the stop")
        return self.poses[-1]


class TestDriveSkeleton(unittest.TestCase):
    node: RclpyNode
    sim: Sim

    @classmethod
    def setUpClass(cls) -> None:
        rclpy.init()
        cls.node = rclpy.create_node("test_drive_skeleton")
        cls.sim = Sim(cls.node)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.node.destroy_node()
        rclpy.shutdown()

    def test_controller_active_and_drives(self) -> None:
        start = self.sim.wait_ready_and_still()
        self.sim.drive(NORMAL_SPEED, 0.0, DRIVES_CHECK_TIME)
        moved = self.sim.stop_and_settle()
        self.assertGreater(math.hypot(moved.x - start.x, moved.y - start.y), DRIVES_CHECK_DISTANCE)

    def test_straight_1m(self) -> None:
        start = self.sim.wait_ready_and_still()
        duration = ramped_duration(
            STRAIGHT_DISTANCE, NORMAL_SPEED, LINEAR_ACCELERATION, LINEAR_DECELERATION
        )
        self.sim.drive(NORMAL_SPEED, 0.0, duration)
        end = self.sim.stop_and_settle()

        dx, dy = end.x - start.x, end.y - start.y
        forward = dx * math.cos(start.yaw) + dy * math.sin(start.yaw)
        sideways = -dx * math.sin(start.yaw) + dy * math.cos(start.yaw)
        self.node.get_logger().info(
            f"straight: {forward:.3f} m forward, {sideways:.3f} m sideways"
        )
        self.assertAlmostEqual(
            forward, STRAIGHT_DISTANCE, delta=STRAIGHT_DISTANCE * STRAIGHT_DISTANCE_TOLERANCE
        )
        self.assertLess(abs(sideways), STRAIGHT_SIDEWAYS_MAX)

    def test_turn_on_the_spot(self) -> None:
        start = self.sim.wait_ready_and_still()
        assert self.sim.now is not None
        began = self.sim.now
        full_turn = self.sim.drive_until(
            0.0, NORMAL_TURN_RATE, lambda: self.sim.turned >= 2 * math.pi, TURN_TIMEOUT
        )
        assert self.sim.now is not None
        took = self.sim.now - began
        end = self.sim.stop_and_settle()

        drift = math.hypot(end.x - start.x, end.y - start.y)
        self.node.get_logger().info(
            f"turn: {self.sim.turned:.3f} rad in {took:.2f} s, centre moved {drift:.3f} m"
        )
        self.assertTrue(full_turn, f"no full turn within {TURN_TIMEOUT:.1f} s")
        self.assertLess(drift, TURN_CENTRE_DRIFT_MAX)

    def test_mixed_commands_stay_stable(self) -> None:
        self.sim.wait_ready_and_still()
        assert sum(seconds for _, _, seconds in MIXED_SEGMENTS) == MIXED_DURATION
        for linear, angular, seconds in MIXED_SEGMENTS:
            self.sim.drive(linear, angular, seconds)
        self.sim.stop_and_settle()

        self.node.get_logger().info(
            f"mixed: {self.sim.wheel_samples} joint states, "
            f"top wheel speed {self.sim.max_wheel_speed:.1f} rad/s, "
            f"top wheel acceleration {self.sim.max_wheel_acceleration:.0f} rad/s²"
        )
        self.assertEqual(self.sim.non_finite, [])
        self.assertGreater(self.sim.wheel_samples, 0)
        self.assertLess(self.sim.max_wheel_speed, WHEEL_SPEED_SPIKE)
        self.assertLess(self.sim.max_wheel_acceleration, WHEEL_ACCELERATION_SPIKE)
