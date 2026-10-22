"""Physics seam, Gazebo sim: sim.launch.py sensors:=true in headless Gazebo.

The sim LiDAR, IMU and camera publish on the ROS names the real drivers later use, in the
model's sensor frames. The sensors are off by default; test_sim.py checks that they stay silent.
"""

import unittest

import launch_testing.actions
import pytest
import rclpy
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare
from rclpy.node import Node as RclpyNode
from rclpy.qos import qos_profile_sensor_data
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import Image, Imu, LaserScan

# Topic: (message type, frame ID), as the description declares them.
SENSORS = {
    "/scan": (LaserScan, "lidar_link"),
    "/imu/data": (Imu, "imu_link"),
    "/camera/image_raw": (Image, "camera_optical_link"),
}

# A guard on waiting, not a bound under test: the robot spawns and every sensor publishes.
STARTUP_TIMEOUT = 60.0  # s of sim time after the first /clock


@pytest.mark.launch_test
def generate_test_description() -> LaunchDescription:
    sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([FindPackageShare("stubentiger_sim"), "launch", "sim.launch.py"])
        ),
        launch_arguments={"gui": "false", "sensors": "true"}.items(),
    )
    return LaunchDescription([sim, launch_testing.actions.ReadyToTest()])


class TestSimSensors(unittest.TestCase):
    node: RclpyNode

    @classmethod
    def setUpClass(cls) -> None:
        rclpy.init()
        cls.node = rclpy.create_node("test_sim_sensors")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.node.destroy_node()
        rclpy.shutdown()

    def test_sensors_publish_in_their_frames(self) -> None:
        now: list[float] = []
        self.node.create_subscription(
            Clock, "/clock", lambda msg: now.append(msg.clock.sec + msg.clock.nanosec * 1e-9), 10
        )
        frames: dict[str, str] = {}
        for topic, (msg_type, _) in SENSORS.items():
            self.node.create_subscription(
                msg_type,
                topic,
                lambda msg, topic=topic: frames.setdefault(topic, msg.header.frame_id),
                qos_profile_sensor_data,
            )

        while not now:
            rclpy.spin_once(self.node, timeout_sec=0.1)
        start = now[-1]
        while len(frames) < len(SENSORS) and now[-1] - start < STARTUP_TIMEOUT:
            rclpy.spin_once(self.node, timeout_sec=0.01)

        self.assertEqual(frames, {topic: frame for topic, (_, frame) in SENSORS.items()})
