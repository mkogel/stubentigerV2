#!/usr/bin/env bash
# Checks that the dev image has the toolchain the v0.1.0 spec lists (#24, "Dev image").
# Run inside the image with ROS sourced; prints every missing item and fails if any.
set -uo pipefail

missing=0
for tool in pre-commit ruff mypy pio clang-format clang-tidy run-clang-tidy gitleaks \
  xmllint ccache colcon rosdep xacro check_urdf glxinfo gz rviz2; do
  command -v "$tool" > /dev/null || { echo "missing tool: $tool"; missing=1; }
done
for pkg in rviz2 ros_gz_sim ros_gz_bridge controller_manager gz_ros2_control \
  diff_drive_controller gpio_controllers joint_state_broadcaster mock_components \
  joy teleop_twist_joy twist_mux foxglove_bridge; do
  ros2 pkg prefix "$pkg" > /dev/null 2>&1 || { echo "missing ROS package: $pkg"; missing=1; }
done
if [ "$(getent passwd 1000 | cut -d: -f1)" != ubuntu ]; then
  echo "uid 1000 is not ubuntu"
  missing=1
fi
[ "$missing" = 0 ] && echo "Dev image has the full toolchain."
exit "$missing"
