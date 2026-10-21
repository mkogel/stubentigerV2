"""The one common launch for all three backends: the robot model, its controllers and Teleop.

hardware:=mock (CI) and later hardware:=real (the Pi) start ros2_control_node and the gpio
broadcaster. With hardware:=gazebo the controller manager runs inside the Gazebo process
(gz_ros2_control), so the sim launch starts Gazebo, spawns the robot and includes this with
use_sim_time:=true; Gazebo has no gpio. Everything else is the same on every backend.

Teleop chain, TwistStamped end to end with no relay node (#24, "Teleop chain"):
/joy → teleop_twist_joy → /cmd_vel_teleop → twist_mux → /diff_drive_controller/cmd_vel.
One process per node, no composition, no namespace.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.condition import Condition
from launch.conditions import UnlessCondition
from launch.substitutions import (
    Command,
    EqualsSubstitution,
    LaunchConfiguration,
    PathJoinSubstitution,
)
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    hardware = LaunchConfiguration("hardware")
    use_sim_time = ParameterValue(LaunchConfiguration("use_sim_time"), value_type=bool)
    not_on_gazebo = UnlessCondition(EqualsSubstitution(hardware, "gazebo"))

    def config(name: str) -> PathJoinSubstitution:
        return PathJoinSubstitution([FindPackageShare("stubentiger_bringup"), "config", name])

    controllers = config("controllers.yaml")
    xacro_file = PathJoinSubstitution(
        [FindPackageShare("stubentiger_description"), "urdf", "stubentiger.urdf.xacro"]
    )
    robot_description = ParameterValue(
        Command(
            ["xacro ", xacro_file, " hardware:=", hardware, " controllers_file:=", controllers]
        ),
        value_type=str,
    )

    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        parameters=[{"robot_description": robot_description, "use_sim_time": use_sim_time}],
    )
    ros2_control_node = Node(
        package="controller_manager",
        executable="ros2_control_node",
        parameters=[controllers, {"use_sim_time": use_sim_time}],
        remappings=[("~/robot_description", "/robot_description")],
        condition=not_on_gazebo,
    )

    def spawner(name: str, remap: str | None = None, condition: Condition | None = None) -> Node:
        arguments = [name] if remap is None else [name, "--controller-ros-args", f"-r {remap}"]
        return Node(
            package="controller_manager",
            executable="spawner",
            arguments=arguments,
            parameters=[{"use_sim_time": use_sim_time}],
            condition=condition,
        )

    joint_state_broadcaster = spawner("joint_state_broadcaster")
    diff_drive_controller = spawner("diff_drive_controller", "/diff_drive_controller/odom:=/odom")
    # GpioCommandController with no command interfaces: a pure broadcaster of the gpio states.
    gpio_state_broadcaster = spawner(
        "gpio_state_broadcaster",
        "/gpio_state_broadcaster/gpio_states:=/gpio_states",
        condition=not_on_gazebo,
    )

    game_controller = Node(
        package="joy",
        executable="game_controller_node",
        parameters=[config("joy.yaml"), {"use_sim_time": use_sim_time}],
    )
    teleop = Node(
        package="teleop_twist_joy",
        executable="teleop_node",
        name="teleop_twist_joy_node",
        parameters=[config("teleop.yaml"), {"use_sim_time": use_sim_time}],
        remappings=[("cmd_vel", "/cmd_vel_teleop")],
    )
    twist_mux = Node(
        package="twist_mux",
        executable="twist_mux",
        parameters=[config("twist_mux.yaml"), {"use_sim_time": use_sim_time}],
        remappings=[("cmd_vel_out", "/diff_drive_controller/cmd_vel")],
    )
    foxglove_bridge = Node(
        package="foxglove_bridge",
        executable="foxglove_bridge",
        parameters=[{"use_sim_time": use_sim_time}],
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "hardware",
                choices=["gazebo", "real", "mock"],
                description="The ros2_control backend: gazebo (sim), real (the Pi) or mock (CI)",
            ),
            DeclareLaunchArgument(
                "use_sim_time", default_value="false", description="Use /clock (Gazebo)"
            ),
            robot_state_publisher,
            ros2_control_node,
            joint_state_broadcaster,
            diff_drive_controller,
            gpio_state_broadcaster,
            game_controller,
            teleop,
            twist_mux,
            foxglove_bridge,
        ]
    )
