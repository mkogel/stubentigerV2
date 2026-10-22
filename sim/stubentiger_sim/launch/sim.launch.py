"""The Virtual MVP in one command: Gazebo, the robot and the whole Teleop stack.

Starts the Gazebo server on the plain floor world, spawns the robot from robot_description, bridges
/clock (and the sensor topics with sensors:=true) and includes robot.launch.py hardware:=gazebo
use_sim_time:=true, so the robot drives through the full Teleop chain. The controller manager runs
inside the Gazebo process (gz_ros2_control), so there is no ros2_control_node.

Switches:
  gui      true starts the Gazebo GUI as its own process next to the server, which contains the
           WSLg GUI memory leak; false runs the server alone, headless (CI).
  rviz     true opens RViz2 with the committed view: robot model, TF and /odom.
  sensors  true adds the sim LiDAR, IMU and camera and bridges /scan, /imu/data and
           /camera/image_raw.
"""

from typing import Any

from launch import LaunchDescription
from launch.actions import (
    AppendEnvironmentVariable,
    DeclareLaunchArgument,
    ExecuteProcess,
    IncludeLaunchDescription,
    Shutdown,
)
from launch.conditions import IfCondition, UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import EnvironmentVariable, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    gui = LaunchConfiguration("gui")
    rviz = LaunchConfiguration("rviz")
    sensors = LaunchConfiguration("sensors")

    def share(package: str, *path: str) -> PathJoinSubstitution:
        return PathJoinSubstitution([FindPackageShare(package), *path])

    # Gazebo finds package:// meshes on its resource path, as <path>/<package>/<file>, and system
    # plugins such as gz_ros2_control-system on its plugin path (as ros_gz_sim's launch does).
    mesh_path = AppendEnvironmentVariable(
        "GZ_SIM_RESOURCE_PATH", share("stubentiger_description", "..")
    )
    plugin_path = AppendEnvironmentVariable(
        "GZ_SIM_SYSTEM_PLUGIN_PATH", EnvironmentVariable("LD_LIBRARY_PATH", default_value="")
    )

    # `gz sim` runs directly, not through ros_gz_sim's gz_sim.launch.py: that one starts it in a
    # shell, so shutdown signals reach only the shell and the server lives on after the launch
    # (the next launch then spawns its robot into the old world).
    def gazebo(*args: str | PathJoinSubstitution, **kwargs: Any) -> ExecuteProcess:
        return ExecuteProcess(
            cmd=["gz", "sim", "-v", "2", *args, "--force-version", "8"], output="screen", **kwargs
        )

    # The server ends the launch when it exits. Without the GUI it renders headless through EGL
    # (software rendering without a GPU).
    world = share("stubentiger_sim", "worlds", "floor.sdf")
    gazebo_server = gazebo("-s", "-r", world, on_exit=Shutdown(), condition=IfCondition(gui))
    gazebo_server_headless = gazebo(
        "-s",
        "-r",
        "--headless-rendering",
        world,
        on_exit=Shutdown(),
        condition=UnlessCondition(gui),
    )
    gazebo_gui = gazebo("-g", condition=IfCondition(gui))
    robot = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(share("stubentiger_bringup", "launch", "robot.launch.py")),
        launch_arguments={
            "hardware": "gazebo",
            "use_sim_time": "true",
            "sensors": sensors,
        }.items(),
    )
    spawn = Node(
        package="ros_gz_sim",
        executable="create",
        arguments=["-topic", "robot_description", "-name", "stubentiger", "-z", "0.001"],
    )
    bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        parameters=[{"config_file": share("stubentiger_sim", "config", "bridge.yaml")}],
    )
    sensors_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        name="sensors_bridge",
        parameters=[{"config_file": share("stubentiger_sim", "config", "sensors_bridge.yaml")}],
        condition=IfCondition(sensors),
    )
    rviz2 = Node(
        package="rviz2",
        executable="rviz2",
        arguments=["-d", share("stubentiger_sim", "rviz", "stubentiger.rviz")],
        parameters=[{"use_sim_time": True}],
        condition=IfCondition(rviz),
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "gui", default_value="true", description="Start the Gazebo GUI (own process)"
            ),
            DeclareLaunchArgument(
                "rviz", default_value="false", description="Open RViz2 with the committed view"
            ),
            DeclareLaunchArgument(
                "sensors", default_value="false", description="Add and bridge the sim sensors"
            ),
            mesh_path,
            plugin_path,
            gazebo_server,
            gazebo_server_headless,
            gazebo_gui,
            robot,
            spawn,
            bridge,
            sensors_bridge,
            rviz2,
        ]
    )
