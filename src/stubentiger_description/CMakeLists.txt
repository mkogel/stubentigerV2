cmake_minimum_required(VERSION 3.8)
project(stubentiger_description)

find_package(ament_cmake REQUIRED)

install(DIRECTORY meshes urdf DESTINATION share/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(test_skeleton_urdf test/test_skeleton_urdf.py)
endif()

ament_package()
