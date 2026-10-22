cmake_minimum_required(VERSION 3.8)
project(stubentiger_sim)

find_package(ament_cmake REQUIRED)

install(DIRECTORY config launch rviz worlds DESTINATION share/${PROJECT_NAME})

# Headless Gazebo tests carry the ctest label `gazebo`: the `sim` CI job runs them,
# `build-test` skips them (`--ctest-args -LE gazebo`).
if(BUILD_TESTING)
  find_package(launch_testing_ament_cmake REQUIRED)
  add_launch_test(test/test_sim.py TARGET test_sim TIMEOUT 600)
  set_tests_properties(test_sim PROPERTIES LABELS gazebo)
  add_launch_test(test/test_sim_sensors.py TARGET test_sim_sensors TIMEOUT 600)
  set_tests_properties(test_sim_sensors PROPERTIES LABELS gazebo)
endif()

ament_package()
