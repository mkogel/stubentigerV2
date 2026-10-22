"""Physics seam, Gazebo sim: sim.launch.py in headless Gazebo, driven through the Teleop chain.

A scripted /joy goes through the whole chain (teleop_twist_joy, twist_mux, diff_drive_controller
inside Gazebo); the stability run injects TwistStamped on /cmd_vel_teleop instead, to reach the
0.7 m/s ceiling that Turbo stays under. Driving is judged on the body's true pose from Gazebo,
bridged for this test, never on /odom (which would hide slip). All time is sim time from /clock
and message stamps. Every test starts from rest and measures relative to where it starts, so the
tests run in any order on the one Gazebo instance.
"""

import math
import unittest
from collections.abc import Callable, Iterable
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
from launch_testing.proc_info_handler import ActiveProcInfoHandler
from nav_msgs.msg import Odometry
from rclpy.node import Node as RclpyNode
from rclpy.qos import qos_profile_sensor_data
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import Image, Imu, JointState, Joy, LaserScan

# robot.launch.py's nodes; the controller manager runs inside the Gazebo process.
NODES = (
    "robot_state_publisher",
    "twist_mux",
    "game_controller_node",
    "teleop_twist_joy_node",
    "foxglove_bridge",
)
CONTROLLERS = ("joint_state_broadcaster", "diff_drive_controller")
WHEEL_JOINTS = (
    "left_wheel_joint",
    "left_wheel_2_joint",
    "left_wheel_3_joint",
    "right_wheel_joint",
    "right_wheel_2_joint",
    "right_wheel_3_joint",
)
# The sim sensors, published only with sensors:=true.
SENSOR_TOPICS = {"/scan": LaserScan, "/imu/data": Imu, "/camera/image_raw": Image}

# The SDL game-controller layout (game_controller_node), as Dev laptop setup confirmed it.
JOY_AXES = 6
JOY_BUTTONS = 21
LB = 9  # Dead-man button
RB = 10  # Turbo
LEFT_STICK_Y = 1  # speed
RIGHT_STICK_X = 2  # turn rate
JOY_PERIOD = 0.05  # s, game_controller_node's 20 Hz autorepeat

# Decided values (#24): speeds in m/s and rad/s, distances in m, times in s of sim time.
NORMAL_SPEED = 0.3
NORMAL_TURN_RATE = 1.2
STRAIGHT_DISTANCE = 1.0
STRAIGHT_DISTANCE_TOLERANCE = 0.10  # ±10 % of the distance
STRAIGHT_SIDEWAYS_MAX = 0.05
TURN_CENTRE_DRIFT_MAX = 0.05
TURBO_SPEED = 0.6
LINEAR_ACCELERATION = 1.0  # diff_drive_controller's ramps, the robot-wide ceiling
LINEAR_DECELERATION = 2.0
CMD_VEL_TIMEOUT = 0.5
JOY_LOSS_STOP_BOUND = CMD_VEL_TIMEOUT + TURBO_SPEED / LINEAR_DECELERATION  # 0.80 s
MIXED_DURATION = 60.0
# The fastest a wheel speed may change under the controller's ramps is a full brake while
# turning: 2.0 m/s² plus 8.0 rad/s² at half the track separation.
ANGULAR_DECELERATION = 8.0
WHEEL_RADIUS = 0.01966
WHEEL_SEPARATION = 0.190
WHEEL_ACCELERATION_MAX = (
    LINEAR_DECELERATION + ANGULAR_DECELERATION * WHEEL_SEPARATION / 2
) / WHEEL_RADIUS  # rad/s²
WHEEL_VELOCITY_LIMIT = 48.2  # the wheel joints' velocity limit, the motor's no-load speed

# Named slack.
CONTROL_PERIOD = 0.02  # one cycle of the 50 Hz controller manager
# One cycle + 200 ms, where mock allows one cycle + 100 ms: the stop is judged on the body, which
# coasts and rocks a little after its wheels stop.
GAZEBO_STOP_SLACK = CONTROL_PERIOD + 0.2
STOPPED_SPEED = 0.01  # m/s: the body counts as stopped below this
ODOM_STAMP_SLACK = 1.0  # s: /odom is stamped in sim time, within this of the last /clock
# Skid steering turns slower than commanded (about 85 % here), so the turn is held until the
# true pose has turned a full 2π, within twice the time a slip-free turn would take.
TURN_TIME_SLACK = 1.0
TURN_TIMEOUT = 2 * math.pi / NORMAL_TURN_RATE * (1 + TURN_TIME_SLACK)
WHEEL_SPEED_SLACK = 0.10  # a spike is any wheel faster than its limit + 10 %
WHEEL_SPEED_SPIKE = WHEEL_VELOCITY_LIMIT * (1 + WHEEL_SPEED_SLACK)
# DART may clamp a wheel at its velocity limit, so a jolt also counts: a wheel speed changing
# faster than the controller's ramps allow, with slack for contact and the mimic wheels' lag.
WHEEL_ACCELERATION_SLACK = 1.0
WHEEL_ACCELERATION_SPIKE = WHEEL_ACCELERATION_MAX * (1 + WHEEL_ACCELERATION_SLACK)

# The test procedure.
HOLD_TIME = 1.5  # s at Turbo: past the 0.6 s ramp, at full speed
SENSOR_SILENCE = 2.0  # s: longer than a few periods of the slowest sensor (the 5.5 Hz LiDAR)
INJECT_PERIOD = 0.02  # s, injected twists at the controller rate
# Mixed driving, injected on /cmd_vel_teleop: (linear m/s, angular rad/s, seconds), up to Turbo
# and the ceiling, with sudden reversals and pivots. 60 s in all.
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

# Guards on waiting, not bounds under test.
STARTUP_TIMEOUT = 60.0  # s of sim time after the first /clock
SETTLE_TIMEOUT = 10.0
SERVICE_CALL_TIMEOUT = 5.0
STILL_WINDOW = 0.5  # at rest: moved less than STILL_DISTANCE over this window
STILL_DISTANCE = 0.001
STILL_ANGLE = 0.005


@pytest.mark.launch_test
def generate_test_description() -> LaunchDescription:
    sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([FindPackageShare("stubentiger_sim"), "launch", "sim.launch.py"])
        ),
        launch_arguments={"gui": "false"}.items(),
    )
    true_pose_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        arguments=["/model/stubentiger/pose@geometry_msgs/msg/PoseStamped[gz.msgs.Pose"],
    )
    return LaunchDescription([sim, true_pose_bridge, launch_testing.actions.ReadyToTest()])


@dataclass
class Pose2D:
    stamp: float
    x: float
    y: float
    yaw: float


def stamp_seconds(stamp: Time) -> float:
    return stamp.sec + stamp.nanosec * 1e-9


def stamp_of(seconds: float) -> Time:
    return Time(sec=int(seconds), nanosec=int((seconds - int(seconds)) * 1e9))


def ramped_duration(target: float, rate: float, accel: float, decel: float) -> float:
    """How long to hold `rate` so the ramped motion covers `target`.

    The ramp up loses rate²/(2·accel) against an instant start; the ramp down after the release
    adds rate²/(2·decel).
    """
    return (target + rate**2 / (2 * accel) - rate**2 / (2 * decel)) / rate


class Sim:
    """The test's view of the running sim: sim time, the true pose, wheel states, inputs."""

    def __init__(self, node: RclpyNode) -> None:
        self.node = node
        self.now: float | None = None
        self.poses: list[Pose2D] = []
        self.turned = 0.0  # unwrapped yaw since the last reset
        self.odom: Odometry | None = None  # the last /odom
        self.max_wheel_speed = 0.0
        self.max_wheel_acceleration = 0.0
        self.wheel_samples = 0
        self.non_finite: list[str] = []
        self._last_wheel: dict[str, tuple[float, float]] = {}  # name: (stamp, velocity)
        self.last_joy = 0.0  # the stamp of the last /joy
        self.joy = node.create_publisher(Joy, "/joy", 10)
        self.inject_pub = node.create_publisher(TwistStamped, "/cmd_vel_teleop", 10)
        self.list_controllers = node.create_client(
            ListControllers, "/controller_manager/list_controllers"
        )
        node.create_subscription(Clock, "/clock", self._on_clock, 10)
        node.create_subscription(PoseStamped, "/model/stubentiger/pose", self._on_pose, 50)
        node.create_subscription(Odometry, "/odom", self._on_odom, 10)
        node.create_subscription(JointState, "/joint_states", self._on_joints, 50)

    def _on_clock(self, msg: Clock) -> None:
        self.now = stamp_seconds(msg.clock)

    def _on_pose(self, msg: PoseStamped) -> None:
        p, q = msg.pose.position, msg.pose.orientation
        if not all(math.isfinite(v) for v in (p.x, p.y, p.z, q.x, q.y, q.z, q.w)):
            self.non_finite.append(f"true pose at {stamp_seconds(msg.header.stamp):.3f} s")
            return
        yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        if self.poses:
            step = yaw - self.poses[-1].yaw
            self.turned += math.atan2(math.sin(step), math.cos(step))
        self.poses.append(Pose2D(stamp_seconds(msg.header.stamp), p.x, p.y, yaw))
        del self.poses[:-500]

    def _on_odom(self, msg: Odometry) -> None:
        self.odom = msg

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

    def controller_states(self) -> dict[str, str]:
        if not self.list_controllers.service_is_ready():
            return {}
        future = self.list_controllers.call_async(ListControllers.Request())
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=SERVICE_CALL_TIMEOUT)
        response = future.result()
        return {} if response is None else {c.name: c.state for c in response.controller}

    def controllers_active(self) -> bool:
        states = self.controller_states()
        return all(states.get(c) == "active" for c in CONTROLLERS)

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
        return self.poses[-1]

    def send_joy(
        self, buttons: Iterable[int] = (), linear: float = 0.0, angular: float = 0.0
    ) -> None:
        """Publish one /joy with these buttons held and stick values, stamped in sim time."""
        assert self.now is not None
        msg = Joy()
        msg.header.stamp = stamp_of(self.now)
        msg.axes = [0.0] * JOY_AXES
        msg.axes[LEFT_STICK_Y] = linear
        msg.axes[RIGHT_STICK_X] = angular
        msg.buttons = [0] * JOY_BUTTONS
        for button in buttons:
            msg.buttons[button] = 1
        self.joy.publish(msg)
        self.last_joy = self.now

    def hold_until(
        self,
        done: Callable[[], bool],
        duration: float,
        buttons: Iterable[int] = (),
        linear: float = 0.0,
        angular: float = 0.0,
    ) -> bool:
        """Stream /joy at the autorepeat rate until `done()` or for `duration` s of sim time.

        Returns whether `done()` was reached.
        """
        buttons = tuple(buttons)
        assert self.now is not None
        end = self.now + duration
        next_joy = self.now
        while self.now < end:
            if done():
                return True
            if self.now >= next_joy:
                self.send_joy(buttons, linear, angular)
                next_joy += JOY_PERIOD
            rclpy.spin_once(self.node, timeout_sec=0.01)
        return False

    def hold(
        self,
        duration: float,
        buttons: Iterable[int] = (),
        linear: float = 0.0,
        angular: float = 0.0,
    ) -> None:
        self.hold_until(lambda: False, duration, buttons, linear, angular)

    def inject(self, linear: float, angular: float, duration: float) -> None:
        """Publish TwistStamped onto /cmd_vel_teleop at the controller rate for `duration` s."""
        assert self.now is not None
        end = self.now + duration
        next_send = self.now
        while self.now < end:
            if self.now >= next_send:
                msg = TwistStamped()
                msg.header.stamp = stamp_of(self.now)
                msg.header.frame_id = "base_footprint"
                msg.twist.linear.x = linear
                msg.twist.angular.z = angular
                self.inject_pub.publish(msg)
                next_send += INJECT_PERIOD
            rclpy.spin_once(self.node, timeout_sec=0.01)

    def idle(self, duration: float) -> None:
        """Spin for `duration` s of sim time without publishing anything."""
        assert self.now is not None
        end = self.now + duration
        while self.now < end:
            rclpy.spin_once(self.node, timeout_sec=0.01)

    def stopped_at(self, since: float) -> float | None:
        """The stamp from which the body stays stopped, if it stopped after `since`."""
        stopped = None
        poses = [p for p in self.poses if p.stamp >= since]
        for a, b in zip(poses, poses[1:]):
            if math.hypot(b.x - a.x, b.y - a.y) / (b.stamp - a.stamp) >= STOPPED_SPEED:
                stopped = None
            elif stopped is None:
                stopped = a.stamp
        return stopped

    def release_and_settle(self) -> Pose2D:
        """Release every button, keep /joy alive and wait for the body to come to rest."""
        self.hold_until(self.at_rest, SETTLE_TIMEOUT)
        self.spin_until(self.at_rest, SETTLE_TIMEOUT, "body at rest after the release")
        return self.poses[-1]


class TestSim(unittest.TestCase):
    node: RclpyNode
    sim: Sim

    @classmethod
    def setUpClass(cls) -> None:
        rclpy.init()
        cls.node = rclpy.create_node("test_sim")
        cls.sim = Sim(cls.node)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.node.destroy_node()
        rclpy.shutdown()

    def test_brings_up_the_robot_on_gazebo(self, proc_info: ActiveProcInfoHandler) -> None:
        self.sim.wait_ready_and_still()  # spawned: Gazebo publishes its true pose
        running = [name for name, _ in self.node.get_node_names_and_namespaces()]
        for name in NODES:
            self.assertIn(name, running)
        # The only controller manager is the one inside Gazebo (gz_ros2_control).
        self.assertEqual(running.count("controller_manager"), 1, running)
        self.assertFalse(
            [p for p in proc_info.process_names() if p.startswith("ros2_control_node")],
            proc_info.process_names(),
        )
        # robot.launch.py runs with use_sim_time:=true: /odom carries sim time.
        self.sim.spin_until(
            lambda: self.sim.odom is not None, SETTLE_TIMEOUT, "a message on /odom"
        )
        assert self.sim.now is not None and self.sim.odom is not None
        odom_stamp = stamp_seconds(self.sim.odom.header.stamp)
        self.assertAlmostEqual(odom_stamp, self.sim.now, delta=ODOM_STAMP_SLACK)

    def test_sensors_off_by_default(self) -> None:
        received: list[str] = []
        subscriptions = [
            self.node.create_subscription(
                msg_type,
                topic,
                lambda _msg, topic=topic: received.append(topic),
                qos_profile_sensor_data,
            )
            for topic, msg_type in SENSOR_TOPICS.items()
        ]
        self.sim.wait_ready_and_still()
        self.sim.idle(SENSOR_SILENCE)
        for subscription in subscriptions:
            self.node.destroy_subscription(subscription)
        self.assertEqual(received, [])

    def test_teleop_straight_1m(self) -> None:
        start = self.sim.wait_ready_and_still()
        duration = ramped_duration(
            STRAIGHT_DISTANCE, NORMAL_SPEED, LINEAR_ACCELERATION, LINEAR_DECELERATION
        )
        self.sim.hold(duration, (LB,), 1.0, 0.0)
        end = self.sim.release_and_settle()

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

    def test_teleop_turn_on_the_spot(self) -> None:
        start = self.sim.wait_ready_and_still()
        assert self.sim.now is not None
        began = self.sim.now
        full_turn = self.sim.hold_until(
            lambda: self.sim.turned >= 2 * math.pi, TURN_TIMEOUT, (LB,), 0.0, 1.0
        )
        assert self.sim.now is not None
        took = self.sim.now - began
        end = self.sim.release_and_settle()

        drift = math.hypot(end.x - start.x, end.y - start.y)
        self.node.get_logger().info(
            f"turn: {self.sim.turned:.3f} rad in {took:.2f} s, centre moved {drift:.3f} m"
        )
        self.assertTrue(full_turn, f"no full turn within {TURN_TIMEOUT:.1f} s")
        self.assertLess(drift, TURN_CENTRE_DRIFT_MAX)

    def test_joy_loss_stops(self) -> None:
        self.sim.wait_ready_and_still()
        self.sim.hold(HOLD_TIME, (LB, RB), 1.0, 0.0)
        last = self.sim.last_joy

        # The controller goes silent with LB and RB held.
        self.sim.idle(JOY_LOSS_STOP_BOUND + GAZEBO_STOP_SLACK + STILL_WINDOW)
        stopped = self.sim.stopped_at(last)
        self.sim.release_and_settle()

        assert stopped is not None, "the body did not stop"
        self.node.get_logger().info(f"/joy loss: body stopped after {stopped - last:.3f} s")
        self.assertLessEqual(stopped - last, JOY_LOSS_STOP_BOUND + GAZEBO_STOP_SLACK)

    def test_mixed_driving_stays_stable(self) -> None:
        self.sim.wait_ready_and_still()
        self.sim.reset_wheel_stats()
        assert sum(seconds for _, _, seconds in MIXED_SEGMENTS) == MIXED_DURATION
        for linear, angular, seconds in MIXED_SEGMENTS:
            self.sim.inject(linear, angular, seconds)
        self.sim.inject(0.0, 0.0, STILL_WINDOW)
        self.sim.spin_until(self.sim.at_rest, SETTLE_TIMEOUT, "body at rest after the stop")

        self.node.get_logger().info(
            f"mixed: {self.sim.wheel_samples} joint states, "
            f"top wheel speed {self.sim.max_wheel_speed:.1f} rad/s, "
            f"top wheel acceleration {self.sim.max_wheel_acceleration:.0f} rad/s²"
        )
        self.assertEqual(self.sim.non_finite, [])
        self.assertGreater(self.sim.wheel_samples, 0)
        self.assertLess(self.sim.max_wheel_speed, WHEEL_SPEED_SPIKE)
        self.assertLess(self.sim.max_wheel_acceleration, WHEEL_ACCELERATION_SPIKE)
