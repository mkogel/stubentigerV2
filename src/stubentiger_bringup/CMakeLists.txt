cmake_minimum_required(VERSION 3.8)
project(stubentiger_bringup)

find_package(ament_cmake REQUIRED)

install(DIRECTORY config launch DESTINATION share/${PROJECT_NAME})

# The behaviour tests run robot.launch.py hardware:=mock (the `mock` layer), so they need
# neither Gazebo nor the Xbox controller and run in build-test and robot-arm64.
if(BUILD_TESTING)
  find_package(launch_testing_ament_cmake REQUIRED)
  add_launch_test(test/test_bringup.py TARGET test_bringup TIMEOUT 300)
  add_launch_test(test/test_teleop.py TARGET test_teleop TIMEOUT 300)
endif()

ament_package()
