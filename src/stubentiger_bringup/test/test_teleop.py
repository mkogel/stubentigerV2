"""Main seam, Teleop: robot.launch.py hardware:=mock under launch_testing.

A scripted sensor_msgs/Joy stream goes in on /joy (or TwistStamped straight onto
/cmd_vel_teleop), and the test reads what comes out: the Teleop twist on /cmd_vel_teleop and the
wheel velocities in /joint_states, which GenericSystem mirrors from the commands
diff_drive_controller writes. Time bounds are measured on message stamps. Every test starts and
ends with the wheels at rest, so the tests run in any order on the one launch.
"""

import time
import unittest
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import launch_testing.actions
import pytest
import rclpy
from builtin_interfaces.msg import Time
from controller_manager_msgs.srv import ListControllers
from geometry_msgs.msg import TwistStamped
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare
from rclpy.node import Node as RclpyNode
from sensor_msgs.msg import Joy, JointState

# The SDL game-controller layout (game_controller_node), as Dev laptop setup confirmed it.
JOY_AXES = 6
JOY_BUTTONS = 21
LB = 9  # Dead-man button
RB = 10  # Turbo
LEFT_STICK_Y = 1  # speed
RIGHT_STICK_X = 2  # turn rate
JOY_RATE = 20.0  # Hz, game_controller_node's autorepeat_rate

# Decided values (#24): m/s, rad/s, m/s², rad/s², s.
NORMAL_SPEED = 0.3
NORMAL_TURN_RATE = 1.2
TURBO_SPEED = 0.6
TURBO_TURN_RATE = 2.5
CEILING_SPEED = 0.7
LINEAR_ACCELERATION = 1.0
LINEAR_DECELERATION = 2.0
CMD_VEL_TIMEOUT = 0.5
RELEASE_STOP_BOUND = TURBO_SPEED / LINEAR_DECELERATION  # 0.30 s
JOY_LOSS_STOP_BOUND = CMD_VEL_TIMEOUT + RELEASE_STOP_BOUND  # 0.80 s
WHEEL_RADIUS = 0.01966
WHEEL_SEPARATION = 0.190

# Named slack.
CONTROL_PERIOD = 0.02  # one cycle of the 50 Hz controller manager
SLACK = CONTROL_PERIOD + 0.1  # on every time bound
VELOCITY_TOLERANCE = 1e-3  # m/s or rad/s: float rounding through the wheels

# The test procedure.
HOLD_TIME = 1.0  # long enough for every ramp to reach its target (2.5 rad/s at 4 rad/s²)
SETTLE_TIME = 0.5  # the wheels stay at rest this long before a test starts
INJECT_RATE = 50.0  # Hz, injected twists at the controller rate
INJECT_TIME = 1.5  # 2 m/s for longer than the 0.7 s ramp to the ceiling
# Guards on waiting, not bounds under test.
STARTUP_TIMEOUT = 60.0
WAIT_TIMEOUT = 5.0
SERVICE_CALL_TIMEOUT = 5.0
QUEUE_DEPTH = 500  # 10 s of /joint_states, so a slow test process drops nothing


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


def stamp_seconds(stamp: Time) -> float:
    return stamp.sec + stamp.nanosec * 1e-9


@dataclass
class Twist2D:
    """A planar twist at a stamp: linear m/s and angular rad/s."""

    stamp: float
    linear: float
    angular: float

    def is_zero(self) -> bool:
        return self.linear == 0.0 and self.angular == 0.0


class Stack:
    """The test's view of the running stack: /joy and /cmd_vel_teleop in, twists out."""

    def __init__(self, node: RclpyNode) -> None:
        self.node = node
        self.teleop: list[Twist2D] = []  # /cmd_vel_teleop
        self.wheels: list[Twist2D] = []  # the body twist the wheel velocities give
        self.last_input = 0.0  # the stamp of the last /joy or injected twist
        self.joy = node.create_publisher(Joy, "/joy", 10)
        self.inject_pub = node.create_publisher(TwistStamped, "/cmd_vel_teleop", 10)
        self.list_controllers = node.create_client(
            ListControllers, "/controller_manager/list_controllers"
        )
        node.create_subscription(TwistStamped, "/cmd_vel_teleop", self._on_teleop, QUEUE_DEPTH)
        node.create_subscription(JointState, "/joint_states", self._on_joints, QUEUE_DEPTH)

    def _on_teleop(self, msg: TwistStamped) -> None:
        self.teleop.append(
            Twist2D(stamp_seconds(msg.header.stamp), msg.twist.linear.x, msg.twist.angular.z)
        )

    def _on_joints(self, msg: JointState) -> None:
        velocity = dict(zip(msg.name, msg.velocity))
        left, right = velocity["left_wheel_joint"], velocity["right_wheel_joint"]
        self.wheels.append(
            Twist2D(
                stamp_seconds(msg.header.stamp),
                WHEEL_RADIUS * (left + right) / 2,
                WHEEL_RADIUS * (right - left) / WHEEL_SEPARATION,
            )
        )

    def now(self) -> float:
        return self.node.get_clock().now().nanoseconds * 1e-9

    def spin_until(self, done: Callable[[], bool], timeout: float, what: str) -> None:
        deadline = time.monotonic() + timeout
        while not done():
            if time.monotonic() > deadline:
                raise AssertionError(f"{what}: not within {timeout} s")
            rclpy.spin_once(self.node, timeout_sec=0.005)

    def controllers_active(self) -> bool:
        if not self.list_controllers.service_is_ready():
            return False
        future = self.list_controllers.call_async(ListControllers.Request())
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=SERVICE_CALL_TIMEOUT)
        response = future.result()
        if response is None:
            return False
        states = {c.name: c.state for c in response.controller}
        return states.get("diff_drive_controller") == "active" and (
            states.get("joint_state_broadcaster") == "active"
        )

    def at_rest(self) -> bool:
        if not self.wheels:
            return False
        last = self.wheels[-1].stamp
        window = [w for w in self.wheels if last - w.stamp <= SETTLE_TIME]
        return last - self.wheels[0].stamp >= SETTLE_TIME and all(w.is_zero() for w in window)

    def wait_at_rest(self) -> float:
        """Wait for active controllers and still wheels; clears the records, returns now."""
        self.spin_until(self.controllers_active, STARTUP_TIMEOUT, "controllers active")
        self.spin_until(self.at_rest, WAIT_TIMEOUT, "wheels at rest")
        self.teleop.clear()
        self.wheels.clear()
        return self.now()

    def send_joy(
        self, buttons: Iterable[int] = (), linear: float = 0.0, angular: float = 0.0
    ) -> float:
        """Publish one /joy message with these buttons held and stick values; returns its stamp."""
        msg = Joy()
        msg.header.stamp = self.node.get_clock().now().to_msg()
        msg.axes = [0.0] * JOY_AXES
        msg.axes[LEFT_STICK_Y] = linear
        msg.axes[RIGHT_STICK_X] = angular
        msg.buttons = [0] * JOY_BUTTONS
        for button in buttons:
            msg.buttons[button] = 1
        self.joy.publish(msg)
        self.last_input = stamp_seconds(msg.header.stamp)
        return self.last_input

    def hold(
        self,
        duration: float,
        buttons: Iterable[int] = (),
        linear: float = 0.0,
        angular: float = 0.0,
    ) -> float:
        """Stream /joy at the autorepeat rate for `duration` s; returns the first stamp."""
        buttons = tuple(buttons)
        first = self.send_joy(buttons, linear, angular)
        next_send = first + 1 / JOY_RATE
        while self.now() < first + duration:
            if self.now() >= next_send:
                self.send_joy(buttons, linear, angular)
                next_send += 1 / JOY_RATE
            rclpy.spin_once(self.node, timeout_sec=0.005)
        self.catch_up(teleop=bool(buttons))
        return first

    def stop(self) -> None:
        """Release every button and wait for the wheels to come to rest."""
        self.hold(SETTLE_TIME)
        self.spin_until(self.at_rest, WAIT_TIMEOUT, "wheels at rest after the release")

    def idle(self, duration: float) -> None:
        """Spin for `duration` s without publishing anything."""
        end = self.now() + duration
        while self.now() < end:
            rclpy.spin_once(self.node, timeout_sec=0.005)
        self.catch_up()

    def inject(self, linear: float, duration: float) -> None:
        """Publish TwistStamped straight onto /cmd_vel_teleop at 50 Hz for `duration` s."""
        end = self.now() + duration
        next_send = self.now()
        while self.now() < end:
            if self.now() >= next_send:
                msg = TwistStamped()
                msg.header.stamp = self.node.get_clock().now().to_msg()
                msg.header.frame_id = "base_footprint"
                msg.twist.linear.x = linear
                self.inject_pub.publish(msg)
                self.last_input = stamp_seconds(msg.header.stamp)
                next_send += 1 / INJECT_RATE
            rclpy.spin_once(self.node, timeout_sec=0.005)
        self.catch_up(teleop=True)

    def catch_up(self, teleop: bool = False) -> None:
        """Spin until the records hold what the stack published up to now.

        A loaded test process handles messages late, so the newest record may be older than the
        last input. Waits for a wheel sample stamped after now and, with `teleop`, for the Teleop
        twist that answers the last input.
        """
        now = self.now()
        self.spin_until(
            lambda: (
                bool(self.wheels)
                and self.wheels[-1].stamp >= now
                and (
                    not teleop or (bool(self.teleop) and self.teleop[-1].stamp >= self.last_input)
                )
            ),
            WAIT_TIMEOUT,
            "records up to date",
        )

    def wheels_since(self, stamp: float) -> list[Twist2D]:
        return [w for w in self.wheels if w.stamp >= stamp]

    def stopped_at(self, since: float) -> float | None:
        """The stamp from which the wheels stay at rest, if they stopped after `since`."""
        stopped = None
        for w in self.wheels_since(since):
            if not w.is_zero():
                stopped = None
            elif stopped is None:
                stopped = w.stamp
        return stopped


class TestTeleop(unittest.TestCase):
    node: RclpyNode
    stack: Stack

    @classmethod
    def setUpClass(cls) -> None:
        rclpy.init()
        cls.node = rclpy.create_node("test_teleop")
        cls.stack = Stack(cls.node)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.node.destroy_node()
        rclpy.shutdown()

    def assertTwist(self, twist: Twist2D, linear: float, angular: float) -> None:
        self.assertAlmostEqual(twist.linear, linear, delta=VELOCITY_TOLERANCE, msg=twist)
        self.assertAlmostEqual(twist.angular, angular, delta=VELOCITY_TOLERANCE, msg=twist)

    def assertDrives(self, linear: float, angular: float) -> None:
        """The Teleop twist and the wheels' twist both end at (linear, angular)."""
        self.assertTrue(self.stack.teleop, "no twist on /cmd_vel_teleop")
        self.assertTwist(self.stack.teleop[-1], linear, angular)
        self.assertTwist(self.stack.wheels[-1], linear, angular)

    def test_no_button_no_motion(self) -> None:
        start = self.stack.wait_at_rest()
        for linear, angular in ((1.0, 1.0), (-1.0, -1.0), (1.0, -1.0), (0.5, 0.0)):
            self.stack.hold(HOLD_TIME / 2, (), linear, angular)

        moving = [t for t in self.stack.teleop if not t.is_zero()]
        self.assertEqual(moving, [], "a non-zero twist on /cmd_vel_teleop")
        wheels = self.stack.wheels_since(start)
        self.assertTrue(wheels, "no /joint_states")
        self.assertTrue(all(w.is_zero() for w in wheels), "the wheels moved")

    def test_button_with_centred_sticks_zero_twist(self) -> None:
        for button in (LB, RB):
            with self.subTest(button=button):
                start = self.stack.wait_at_rest()
                self.stack.hold(HOLD_TIME, (button,), 0.0, 0.0)

                self.assertTrue(self.stack.teleop, "no twist on /cmd_vel_teleop")
                self.assertTrue(all(t.is_zero() for t in self.stack.teleop))
                self.assertTrue(all(w.is_zero() for w in self.stack.wheels_since(start)))
                self.stack.stop()

    def test_lb_full_stick_normal(self) -> None:
        self.stack.wait_at_rest()
        self.stack.hold(HOLD_TIME, (LB,), 1.0, 1.0)
        self.assertDrives(NORMAL_SPEED, NORMAL_TURN_RATE)
        self.stack.stop()

    def test_turbo_with_lb_and_with_rb_alone(self) -> None:
        for buttons in ((LB, RB), (RB,)):
            with self.subTest(buttons=buttons):
                self.stack.wait_at_rest()
                self.stack.hold(HOLD_TIME, buttons, 1.0, 1.0)
                self.assertDrives(TURBO_SPEED, TURBO_TURN_RATE)
                self.stack.stop()

    def test_turbo_release_back_to_normal(self) -> None:
        self.stack.wait_at_rest()
        self.stack.hold(HOLD_TIME, (LB, RB), 1.0, 1.0)
        self.assertDrives(TURBO_SPEED, TURBO_TURN_RATE)
        self.stack.hold(HOLD_TIME, (LB,), 1.0, 1.0)
        self.assertDrives(NORMAL_SPEED, NORMAL_TURN_RATE)
        self.stack.stop()

    def test_deadman_release_stops(self) -> None:
        self.stack.wait_at_rest()
        self.stack.hold(HOLD_TIME, (LB, RB), 1.0, 0.0)
        self.assertTwist(self.stack.wheels[-1], TURBO_SPEED, 0.0)

        # Both buttons let go (RB alone would still drive), the stick still pushed.
        released = self.stack.hold(RELEASE_STOP_BOUND + SLACK + SETTLE_TIME, (), 1.0, 0.0)
        stopped = self.stack.stopped_at(released)
        assert stopped is not None, "the wheels did not stop"
        self.node.get_logger().info(f"release: wheels at 0 after {stopped - released:.3f} s")
        self.assertLessEqual(stopped - released, RELEASE_STOP_BOUND + SLACK)

    def test_joy_loss_stops(self) -> None:
        self.stack.wait_at_rest()
        self.stack.hold(HOLD_TIME, (LB, RB), 1.0, 0.0)
        last = self.stack.send_joy((LB, RB), 1.0, 0.0)
        self.assertTwist(self.stack.wheels[-1], TURBO_SPEED, 0.0)

        # The controller goes silent with LB (and RB) held.
        self.stack.idle(JOY_LOSS_STOP_BOUND + SLACK + SETTLE_TIME)
        stopped = self.stack.stopped_at(last)
        assert stopped is not None, "the wheels did not stop"
        self.node.get_logger().info(f"/joy loss: wheels at 0 after {stopped - last:.3f} s")
        self.assertLessEqual(stopped - last, JOY_LOSS_STOP_BOUND + SLACK)
        self.stack.stop()

    def test_injected_speed_capped_at_ceiling(self) -> None:
        start = self.stack.wait_at_rest()
        self.stack.inject(2.0, INJECT_TIME)
        self.stack.inject(0.0, HOLD_TIME)
        wheels = self.stack.wheels_since(start)

        top = max(w.linear for w in wheels)
        self.node.get_logger().info(f"injected 2 m/s: top speed {top:.4f} m/s")
        self.assertLessEqual(top, CEILING_SPEED + VELOCITY_TOLERANCE)
        self.assertAlmostEqual(top, CEILING_SPEED, delta=VELOCITY_TOLERANCE)
        self.assertTrue(wheels[-1].is_zero(), wheels[-30:])
        # Between any two samples the speed changes no faster than the ramps allow. A
        # /joint_states sample shows the command of the cycle before, so one cycle of slack.
        too_fast = [
            (a, b)
            for i, a in enumerate(wheels)
            for b in wheels[i + 1 :]
            if b.linear - a.linear
            > LINEAR_ACCELERATION * (b.stamp - a.stamp + CONTROL_PERIOD) + VELOCITY_TOLERANCE
            or a.linear - b.linear
            > LINEAR_DECELERATION * (b.stamp - a.stamp + CONTROL_PERIOD) + VELOCITY_TOLERANCE
        ]
        self.assertEqual(too_fast[:3], [], f"{len(too_fast)} pairs beyond the ramp limits")
