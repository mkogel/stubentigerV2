"""Drivable sim skeleton: headless Gazebo, the robot and its controllers, nothing else.

Starts the Gazebo server on the plain floor world, spawns the robot from robot_description,
bridges /clock and spawns joint_state_broadcaster and diff_drive_controller, which then drives
from TwistStamped on /diff_drive_controller/cmd_vel. The controller manager runs inside the
Gazebo process (gz_ros2_control), so there is no ros2_control_node. Gazebo sim replaces this
with the full sim.launch.py.
"""

from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    xacro_file = PathJoinSubstitution(
        [FindPackageShare("stubentiger_description"), "urdf", "stubentiger.urdf.xacro"]
    )
    controllers = PathJoinSubstitution(
        [FindPackageShare("stubentiger_bringup"), "config", "controllers.yaml"]
    )
    world = PathJoinSubstitution([FindPackageShare("stubentiger_sim"), "worlds", "floor.sdf"])
    robot_description = ParameterValue(
        Command(["xacro ", xacro_file, " controllers_file:=", controllers]), value_type=str
    )

    # Server only, headless; sensors that render use EGL (software rendering without a GPU).
    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([FindPackageShare("ros_gz_sim"), "launch", "gz_sim.launch.py"])
        ),
        launch_arguments={
            "gz_args": ["-s -r -v 2 --headless-rendering ", world],
            "on_exit_shutdown": "true",
        }.items(),
    )
    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        parameters=[{"robot_description": robot_description, "use_sim_time": True}],
    )
    spawn = Node(
        package="ros_gz_sim",
        executable="create",
        arguments=["-topic", "robot_description", "-name", "stubentiger", "-z", "0.001"],
    )
    clock_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        arguments=["/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock"],
    )
    controller_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["joint_state_broadcaster", "diff_drive_controller"],
        parameters=[{"use_sim_time": True}],
    )

    return LaunchDescription(
        [
            gazebo,
            robot_state_publisher,
            spawn,
            clock_bridge,
            RegisterEventHandler(OnProcessExit(target_action=spawn, on_exit=[controller_spawner])),
        ]
    )
