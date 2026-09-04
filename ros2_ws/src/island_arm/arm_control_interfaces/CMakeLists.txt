cmake_minimum_required(VERSION 3.8)
project(arm_control_interfaces)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "srv/MoveJ.srv"
  "srv/MoveL.srv"
  "srv/MoveToPose.srv"
  "srv/MoveJDeg.srv"
  "srv/MoveJRltDeg.srv"
  "srv/Init.srv"
  "srv/GetCurrentPose.srv"
  "action/ExecuteTrajectory.action"
  DEPENDENCIES std_msgs geometry_msgs
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
